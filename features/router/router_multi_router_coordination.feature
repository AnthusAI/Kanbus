Feature: Multi-router coordination guarantees
  As an operator
  I want coordination guarantees stated for soft and hard providers
  So that I know when duplicate package execution is possible

  Background:
    Given two router workers use isolated checkouts of the same Kanbus project
    And both workers plan package "kbs-601" at the same logical revision

  Scenario: Git-only coordination is soft and may admit duplicate work
    Given router coordination mode is "soft"
    And Git is the only coordination provider
    When both router workers start package "kbs-601" during a simulated partition
    Then both workers may report that their claim was accepted
    And the project history should retain both claims
    And publication should still accept only the current claim revision

  Scenario: Hard coordination allows only one router worker to start a package
    Given router coordination mode is "hard"
    And the Mutex API provider is available
    When both router workers request the package claim at the same time
    Then exactly one worker should acquire the package claim
    And the other worker should report "package already claimed"
    And the losing worker should not start an adapter

  Scenario: Hard coordination protects the shared project WIP limit across workers
    Given router coordination mode is "hard"
    And the project WIP limit is 1
    And pending packages "kbs-603, kbs-604" are eligible
    When both router workers run one scheduling pass at the same time
    Then exactly one adapter should start
    And exactly one package should enter the active status
    And the other package should be deferred with reason "project_wip_limit"

  Scenario: Hard coordination does not fall back when the Mutex API is unavailable
    Given coordination providers are configured as "mutex_api,mqtt,git"
    And the Mutex API endpoint is configured but unreachable
    When both router workers attempt package "kbs-601"
    Then neither worker should start an adapter
    And both workers should report "hard router coordination requires Mutex API"
    And both workers should leave package "kbs-601" unchanged

  Scenario: An expired hard claim permits deterministic takeover
    Given router coordination mode is "hard"
    And router worker "worker-a" owns package "kbs-602" claim "claim-a" until "2026-09-17T10:05:00Z"
    When simulated time advances past the claim expiry
    And router worker "worker-b" requests package "kbs-602"
    Then worker "worker-b" should acquire a new claim revision
    And worker "worker-b" should start from the latest accepted checkpoint
    And worker "worker-a" should be unable to publish its obsolete result

  Scenario: An MQTT outage keeps soft routers live through Git polling
    Given coordination providers are configured as "mqtt,git"
    And both router workers are watching with interval 30 seconds
    And the MQTT broker becomes unreachable
    When the workers poll Git history
    Then both workers should observe durable router events from Git
    And both workers should continue planning eligible packages
    And duplicate work may still occur because soft coordination is not hard exclusion
