Feature: Strongest-available coordination provider
  As a Kanbus operator
  I want Kanbus to pick the strongest configured coordination provider automatically
  So that Git-only installs stay fully functional and optional services are progressive enhancement

  Background:
    Given a Kanbus project with default configuration

  Scenario: Git-only coordination remains fully functional
    Given coordination providers are configured as "git"
    When I run "kanbus coordination claim --resource job:dispatch-1 --owner worker-1 --claim-id claim-git"
    Then the command should succeed
    And coordination provider used should be "git"
    And the command exit code should be 0

  Scenario: Missing MQTT broker is not an error for Git-only coordination
    Given coordination providers are configured as "git"
    And realtime MQTT broker is unreachable
    When I run "kanbus coordination claim --resource job:dispatch-2 --owner worker-1 --claim-id claim-no-mqtt"
    Then the command should succeed
    And stderr should not contain "mqtt required"

  Scenario: Missing Mutex API endpoint is not an error for Git-only coordination
    Given coordination providers are configured as "git"
    And coordination mutex API endpoint is unset
    When I run "kanbus coordination claim --resource job:dispatch-3 --owner worker-1 --claim-id claim-no-mutex"
    Then the command should succeed
    And stderr should not contain "mutex api required"

  @wip
  Scenario: Git plus MQTT uses MQTT for fast-path coordination when configured
    Given coordination providers are configured as "git,mqtt"
    And realtime MQTT gossip is available per docs REALTIME.md
    When I run "kanbus coordination claim --resource job:dispatch-4 --owner worker-1 --claim-id claim-fast"
    Then the command should succeed
    And coordination provider used should be "mqtt"
    And Git history for resource "job:dispatch-4" should contain a durable claim event

  @wip
  Scenario: Git plus MQTT plus Mutex API uses Mutex API for hard exclusion when configured
    Given coordination providers are configured as "git,mqtt,mutex_api"
    And coordination mutex API endpoint is "https://mutex.example.test"
    And mutex API accepts acquire for resource "job:dispatch-5"
    When I run "kanbus coordination claim --resource job:dispatch-5 --owner worker-1 --claim-id claim-hard"
    Then the command should succeed
    And coordination provider used should be "mutex_api"

  Scenario: Duplicate work remains acceptable at Git-only strength
    Given coordination providers are configured as "git"
    When worker "worker-a" runs "kanbus coordination claim --resource job:dispatch-6 --owner worker-a --claim-id claim-a"
    And worker "worker-b" runs "kanbus coordination claim --resource job:dispatch-6 --owner worker-b --claim-id claim-b"
    Then both coordination claims for resource "job:dispatch-6" should succeed
    And coordination inspect for resource "job:dispatch-6" should report soft ownership not hard mutex

  Scenario: Coordination claim is not assignee claim on an issue
    Given an issue "kanbus-task-01" of type "task" with status "open"
    And the current user is "dev@example.com"
    When I run "kanbus coordination claim --resource issue:kanbus-task-01 --owner worker-1 --claim-id claim-coord"
    Then issue "kanbus-task-01" should have status "open"
    And issue "kanbus-task-01" should have assignee unset
