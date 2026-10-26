Feature: CLI daemon defaults and connection resilience
  As a Kanbus user
  I want CLI commands to stay off the index daemon unless I opt in
  So that a command never spawns or waits for a background process by default

  Scenario: CLI commands do not spawn or wait for the daemon by default
    Given a Kanbus project with default configuration
    And daemon mode is not configured
    When I run "kanbus create Daemon default off"
    Then the command should succeed
    When I run "kanbus list"
    Then the command should succeed
    And stdout should contain "Daemon default off"
    And no daemon socket should exist for the project

  Scenario: The daemon status command reports the daemon as disabled by default
    Given a Kanbus project with default configuration
    And daemon mode is not configured
    When I run "kanbus daemon-status"
    Then the command should fail with exit code 1
    And stderr should contain "daemon disabled"

  Scenario: A daemon connection error does not stop the daemon
    Given a Kanbus project with default configuration
    And a real daemon is running for the project
    When a client sends a daemon request and closes the connection before the response
    And a client sends half a daemon request and closes the connection
    And I open and close a daemon connection without data
    Then the daemon should still respond to ping
