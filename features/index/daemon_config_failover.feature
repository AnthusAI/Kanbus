Feature: Daemon config schema failover
  As a Kanbus user
  I want the daemon client to restart a stale daemon that rejects the current config schema
  So that I never need KANBUS_NO_DAEMON after config upgrades

  Scenario: Daemon client restarts after config schema rejection
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And the daemon index list fails once with "unknown configuration fields" then succeeds
    When I request a daemon index list
    Then the daemon request should succeed
    And the daemon should have been restarted
