Feature: Daemon lifecycle for just-in-time indexing
  As a Taskulus user
  I want the index daemon to start, recover, and stay fresh automatically
  So that CLI commands are fast and reliable without manual intervention

  Scenario: Auto-spawn daemon when no socket exists
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And the daemon socket does not exist
    When I run "tsk list"
    Then a daemon should be started
    And the client should connect to the daemon socket
    And the command should succeed

  Scenario: Reuse existing daemon socket
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a socket
    When I run "tsk list"
    Then the client should connect without spawning a new daemon
    And the command should succeed

  Scenario: Recover from stale socket
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And a daemon socket exists but no daemon responds
    When I run "tsk list"
    Then the stale socket should be removed
    And a new daemon should be started
    And the command should succeed

  Scenario: No-daemon fallback
    Given a Taskulus project with default configuration
    And daemon mode is disabled
    When I run "tsk list"
    Then the command should run without a daemon
    And the command should succeed

  Scenario: Repair stale index on request
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a stale index
    When I run "tsk list"
    Then the daemon should rebuild the index
    And the command should succeed

  Scenario: Daemon status requires daemon enabled
    Given a Taskulus project with default configuration
    And daemon mode is disabled
    When I run "tsk daemon-status"
    Then the command should fail with exit code 1
    And stderr should contain "daemon disabled"

  Scenario: Daemon stop requires daemon enabled
    Given a Taskulus project with default configuration
    And daemon mode is disabled
    When I run "tsk daemon-stop"
    Then the command should fail with exit code 1
    And stderr should contain "daemon disabled"

  Scenario: Daemon status fails when multiple projects exist
    Given a repository with multiple projects and issues
    And daemon mode is enabled
    When I run "tsk daemon-status"
    Then the command should fail with exit code 1
    And stderr should contain "multiple projects found"

  Scenario: Daemon status reports ok when running
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a socket
    When I run "tsk daemon-status"
    Then the command should succeed
    And stdout should contain "\"status\": \"ok\""

  Scenario: Daemon stop shuts down the server
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a socket
    When I run "tsk daemon-stop"
    Then the command should succeed
    And stdout should contain "\"status\": \"stopping\""
    And the daemon should shut down
