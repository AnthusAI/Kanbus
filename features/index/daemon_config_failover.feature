Feature: Daemon config schema failover
  As a Kanbus user
  I want listing to recover when a stale daemon rejects the current config schema
  So that I never need KANBUS_NO_DAEMON after config upgrades

  Scenario: List falls back to filesystem when daemon rejects config schema
    Given a Kanbus project with default configuration
    And issues "kanbus-dcf1" exist
    And issue "kanbus-dcf1" has title "Daemon config failover marker"
    And daemon mode is enabled
    And the daemon index list responds with "unknown configuration fields"
    When I run "kanbus list"
    Then the command should succeed
    And stdout should contain "Daemon config failover marker"

  Scenario: Daemon client restarts after config schema rejection
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And the daemon index list fails once with "unknown configuration fields" then succeeds
    When I request a daemon index list
    Then the daemon request should succeed
    And the daemon should have been restarted
