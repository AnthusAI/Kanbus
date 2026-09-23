Feature: Issue Router one-shot execution and operator controls
  As an operator
  I want to run and control one deterministic router process
  So that automated work can be started and stopped without losing Kanbus ownership

  Background:
    Given a Kanbus project with valid Codex-first router configuration

  Scenario: One-shot run executes the first eligible package through the configured fake adapter
    Given pending routed packages are ordered "kbs-201, kbs-202"
    And provider profile "codex-default" runs fake adapter outcome "completed"
    When I run "kanbus router run --once"
    Then the command should succeed
    And the adapter should run only package "kbs-201"
    And stdout should equal "Issue Router run completed: started=1 completed=1 review=1 failed=0 deferred=1\n"
    And package "kbs-201" should be in status "review"
    And package "kbs-202" should remain in status "open"

  Scenario: One-shot run without a configured forge completes the package into Review without a pull request
    Given pending routed packages are ordered "kbs-201, kbs-202"
    And provider profile "codex-default" runs fake adapter outcome "completed"
    And the router forge is not configured
    When I run "kanbus router run --once"
    Then the command should succeed
    And the adapter should run only package "kbs-201"
    And stdout should equal "Issue Router run completed: started=1 completed=1 review=1 failed=0 deferred=1\n"
    And package "kbs-201" should be in status "review"
    And no pull request should have been opened

  Scenario: One-shot run with no eligible package succeeds without starting an adapter
    Given there are no eligible router packages
    When I run "kanbus router run --once"
    Then the command should succeed
    And no adapter should have run
    And stdout should equal "Issue Router run completed: started=0 completed=0 review=0 failed=0 deferred=0\n"

  Scenario: Watch mode reconciles immediately and polls GitHub at the configured interval
    Given router watch interval is 30 seconds
    And the router scheduler is stopped
    When I run "kanbus router run --watch"
    Then the command should stay running until stopped
    And the router should reconcile the issue board immediately
    And the router should poll GitHub pull request state every 30 seconds
    And MQTT router notifications should trigger reconciliation before the next poll

  Scenario: MQTT outage falls back to Git polling in watch mode
    Given coordination providers are configured as "mqtt,git"
    And the router is watching with interval 30 seconds
    And the MQTT broker becomes unreachable
    When the router enters its next watch cycle
    Then the router should continue by polling Git history every 30 seconds
    And no package should be marked complete solely because MQTT is unavailable

  Scenario: A hard Mutex API outage fails closed before the adapter starts
    Given coordination providers are configured as "mutex_api,mqtt,git"
    And the Mutex API endpoint is configured but unreachable
    And pending package "kbs-205" is eligible
    When I run "kanbus router run --once"
    Then the command should fail with exit code 1
    And no adapter should have run
    And stderr should equal "error: hard router coordination requires Mutex API; provider mutex_api is unavailable; no package was started\n"

  Scenario: Router pause persists and prevents new starts
    Given the router scheduler is running
    When I run "kanbus router pause"
    Then the command should succeed
    And stdout should equal "Issue Router paused.\n"
    And the router scheduler should remain paused after restart
    When I run "kanbus router run --once"
    Then no adapter should have run
    And stdout should equal "Issue Router run completed: started=0 completed=0 review=0 failed=0 deferred=1\n"

  Scenario: Resume clears the global pause without clearing route holds
    Given the router is paused
    And provider profile "codex-default" is held
    When I run "kanbus router resume"
    Then the command should succeed
    And stdout should equal "Issue Router resumed.\n"
    And the router should not be paused
    And provider profile "codex-default" should remain held

  Scenario: An operator can hold and release one provider profile
    When I run "kanbus router hold --provider-profile codex-default"
    Then the command should succeed
    And stdout should equal "Held route provider-profile:codex-default.\n"
    And packages pinned to provider profile "codex-default" should be deferred with reason "held"
    When I run "kanbus router unhold --provider-profile codex-default"
    Then the command should succeed
    And stdout should equal "Released hold for route provider-profile:codex-default.\n"

  Scenario: An operator can hold and release one agent class
    When I run "kanbus router hold --class implementation"
    Then the command should succeed
    And stdout should equal "Held route class:implementation.\n"
    And class-routed packages for "implementation" should be deferred with reason "held"
    When I run "kanbus router unhold --class implementation"
    Then the command should succeed
    And stdout should equal "Released hold for route class:implementation.\n"

  Scenario: Hold commands require exactly one configured route selector
    When I run "kanbus router hold"
    Then the command should fail with exit code 2
    And stderr should equal "error: select exactly one of --class or --provider-profile\n"

  Scenario: Hold commands reject unknown provider profiles
    When I run "kanbus router hold --provider-profile missing"
    Then the command should fail with exit code 2
    And stderr should equal "error: unknown provider profile \"missing\"\n"

  Scenario: Status reports scheduler, pause, run count, and sorted holds
    Given the router scheduler is running
    And the router is paused
    And provider profile "codex-default" and class "implementation" are held
    And one router package is active
    When I run "kanbus router status"
    Then stdout should equal:
      """
      Issue Router: running
      Scheduling: paused
      Active runs: 1
      Held routes: class:implementation,provider-profile:codex-default
      """

  Scenario: Cancel stops an active package and keeps its latest accepted checkpoint
    Given active package "kbs-210" has claim "claim-210" and accepted checkpoint "refs/kanbus/router/checkpoints/kbs-210"
    And provider profile "codex-default" is running package "kbs-210"
    When I run "kanbus router cancel kbs-210"
    Then the command should succeed
    And the adapter should receive a cancellation request for claim "claim-210"
    And package "kbs-210" should transition to status "blocked"
    And checkpoint "refs/kanbus/router/checkpoints/kbs-210" should remain accepted
    And stdout should equal "Cancelled router package kbs-210; checkpoint refs/kanbus/router/checkpoints/kbs-210 preserved.\n"

  Scenario: Cancel requires an active package
    When I run "kanbus router cancel kbs-211"
    Then the command should fail with exit code 1
    And stderr should equal "error: no active router run for package \"kbs-211\"\n"

  Scenario: Stop lets the current run finish and prevents later starts
    Given the router scheduler is running package "kbs-220"
    When I run "kanbus router stop"
    Then the command should succeed
    And stdout should equal "Issue Router stop requested.\n"
    And package "kbs-220" should be allowed to finish its current adapter call
    And the router scheduler should stop before starting another package

  Scenario: Stop is idempotent when the scheduler is already stopped
    Given the router scheduler is stopped
    When I run "kanbus router stop"
    Then the command should succeed
    And stdout should equal "Issue Router is not running.\n"

  Scenario: Stop releases an acquired scheduler lease after the active run finishes
    Given the router scheduler holds claim "scheduler-1" and runs package "kbs-221"
    When I run "kanbus router stop"
    And package "kbs-221" finishes its current adapter call
    Then the router scheduler should release claim "scheduler-1"
    And the scheduler should not start another package

  Scenario: Pause, holds, and stop are recorded in durable Kanbus history
    When I run "kanbus router pause"
    And I run "kanbus router hold --provider-profile codex-default"
    Then Kanbus history should contain router control events in command order:
      | event         | target                    |
      | router_paused |                           |
      | route_held    | provider-profile:codex-default |
