@wip
Feature: Daemon lifecycle for just-in-time indexing
  As a Taskulus user
  I want the index daemon to start, recover, and stay fresh automatically
  So that CLI commands are fast and reliable without manual intervention

  @wip
  Scenario: Auto-spawn daemon when no socket exists
    Given a Taskulus project with default configuration
    And the daemon socket does not exist
    When I run "tsk list"
    Then a daemon should be started
    And the client should connect to the daemon socket
    And the command should succeed

  @wip
  Scenario: Reuse existing daemon socket
    Given a Taskulus project with default configuration
    And the daemon is running with a socket
    When I run "tsk list"
    Then the client should connect without spawning a new daemon
    And the command should succeed

  @wip
  Scenario: Recover from stale socket
    Given a Taskulus project with default configuration
    And a daemon socket exists but no daemon responds
    When I run "tsk list"
    Then the stale socket should be removed
    And a new daemon should be started
    And the command should succeed

  @wip
  Scenario: No-daemon fallback
    Given a Taskulus project with default configuration
    And daemon mode is disabled
    When I run "tsk list"
    Then the command should run without a daemon
    And the command should succeed

  @wip
  Scenario: Repair stale index on request
    Given a Taskulus project with default configuration
    And the daemon is running with a stale index
    When I run "tsk list"
    Then the daemon should rebuild the index
    And the command should succeed
