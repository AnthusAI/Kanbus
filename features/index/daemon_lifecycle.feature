Feature: Daemon lifecycle for just-in-time indexing
  As a Kanbus user
  I want the index daemon to start, recover, and stay fresh automatically
  So that CLI commands are fast and reliable without manual intervention

  Scenario: Auto-spawn daemon when no socket exists
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And the daemon socket does not exist
    When I run "kanbus list"
    Then a daemon should be started
    And the client should connect to the daemon socket
    And the command should succeed

  Scenario: Reuse existing daemon socket
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a socket
    When I run "kanbus list"
    Then the client should connect without spawning a new daemon
    And the command should succeed

  Scenario: Recover from stale socket
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And a daemon socket exists but no daemon responds
    When I run "kanbus list"
    Then the stale socket should be removed
    And a new daemon should be started
    And the command should succeed

  Scenario: No-daemon fallback
    Given a Kanbus project with default configuration
    And daemon mode is disabled
    When I run "kanbus list"
    Then the command should run without a daemon
    And the command should succeed

  Scenario: Repair stale index on request
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a stale index
    When I run "kanbus list"
    Then the daemon should rebuild the index
    And the command should succeed

  Scenario: Daemon status requires daemon enabled
    Given a Kanbus project with default configuration
    And daemon mode is disabled
    When I run "kanbus daemon-status"
    Then the command should fail with exit code 1
    And stderr should contain "daemon disabled"

  Scenario: Daemon stop requires daemon enabled
    Given a Kanbus project with default configuration
    And daemon mode is disabled
    When I run "kanbus daemon-stop"
    Then the command should fail with exit code 1
    And stderr should contain "daemon disabled"

  Scenario: Daemon status fails when project is missing
    Given an empty git repository
    And daemon mode is enabled
    When I run "kanbus daemon-status"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Daemon status fails when multiple projects exist
    Given a repository with multiple projects and issues
    And daemon mode is enabled
    When I run "kanbus daemon-status"
    Then the command should fail with exit code 1
    And stderr should contain "multiple projects found"

  Scenario: Daemon stop fails when multiple projects exist
    Given a repository with multiple projects and issues
    And daemon mode is enabled
    When I run "kanbus daemon-stop"
    Then the command should fail with exit code 1
    And stderr should contain "multiple projects found"

  Scenario: Daemon status fails when dotfile path is missing
    Given a repository with a .kanbus.yml file referencing a missing path
    And daemon mode is enabled
    When I run "kanbus daemon-status"
    Then the command should fail with exit code 1
    And stderr should contain "kanbus path not found"

  Scenario: Daemon status reports ok when running
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a socket
    When I run "kanbus daemon-status"
    Then the command should succeed
    And stdout should contain "\"status\": \"ok\""

  Scenario: Daemon stop shuts down the server
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a socket
    When I run "kanbus daemon-stop"
    Then the command should succeed
    And stdout should contain "\"status\": \"stopping\""
    And the daemon should shut down

  Scenario: Daemon responds via direct handler
    Given a Kanbus project with default configuration
    When a daemon status request is handled directly
    Then the daemon response should be ok

  Scenario: Daemon client reports empty responses
    Given a Kanbus project with default configuration
    And a daemon socket returns an empty response
    When I request daemon status via the client
    Then the daemon client error should be "empty daemon response"

  Scenario: Daemon client parses ok responses
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And a daemon socket returns a valid response
    When I request daemon status via the client
    Then the daemon response should be ok

  Scenario: Daemon client removes stale socket on retry
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And a daemon socket exists but no daemon responds
    When I request a daemon index list
    Then the daemon socket should be removed
    And the daemon request should succeed
