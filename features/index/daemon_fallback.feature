Feature: Daemon fallback and best-effort start
  As a Kanbus user
  I want the Virtuus daemon to be a just-in-time accelerator only
  So that issue commands always succeed synchronously without it

  Scenario: Issue commands succeed synchronously when no daemon is available
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And the daemon cannot start
    When I run "kanbus create Daemon fallback issue"
    Then the command should succeed
    When I run "kanbus list"
    Then the command should succeed
    And stdout should contain "Daemon fallback issue"

  Scenario: Issue commands use the daemon when it is available
    Given a Kanbus project with default configuration
    And a real daemon is running for the project
    When I run "kanbus create Daemon serving issue"
    Then the command should succeed
    When I run "kanbus list"
    Then the command should succeed
    And stdout should contain "Daemon serving issue"
    And the daemon status should be ok