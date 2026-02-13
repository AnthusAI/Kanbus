Feature: Query and list operations
  As a Taskulus user
  I want to query issues by common fields
  So that I can find the right work quickly

  Scenario: List issues filtered by status
    Given a Taskulus project with default configuration
    And issues "tsk-open" and "tsk-closed" exist
    And issue "tsk-closed" has status "closed"
    When I run "tsk list --status open"
    Then stdout should contain "tsk-open"
    And stdout should not contain "tsk-closed"

  Scenario: List output includes project paths when multiple projects exist
    Given a repository with multiple projects and issues
    When I run "tsk list"
    Then stdout should contain "alpha/project T tsk-alpha"
    And stdout should contain "beta/project T tsk-beta"

  Scenario: List output includes project paths when multiple projects exist without local issues
    Given a repository with multiple projects and issues
    When I run "tsk list --no-local"
    Then stdout should contain "alpha/project T tsk-alpha"
    And stdout should contain "beta/project T tsk-beta"

  Scenario: List output includes project paths for local-only issues in multi-project repositories
    Given a repository with multiple projects and local issues
    When I run "tsk list --local-only"
    Then stdout should contain "alpha/project T tsk-alpha-local"
    And stdout should not contain "beta/project T tsk-beta"

  Scenario: List output includes external project paths from dotfile
    Given a repository with a .taskulus file referencing another project
    When I run "tsk list"
    Then stdout should contain the external project path for "tsk-external"

  Scenario: List issues filtered by type
    Given a Taskulus project with default configuration
    And issues "tsk-task" and "tsk-bug" exist
    And issue "tsk-bug" has type "bug"
    When I run "tsk list --type task"
    Then stdout should contain "tsk-task"
    And stdout should not contain "tsk-bug"

  Scenario: List issues filtered by assignee
    Given a Taskulus project with default configuration
    And issues "tsk-a" and "tsk-b" exist
    And issue "tsk-a" has assignee "dev@example.com"
    When I run "tsk list --assignee dev@example.com"
    Then stdout should contain "tsk-a"
    And stdout should not contain "tsk-b"

  Scenario: List issues filtered by label
    Given a Taskulus project with default configuration
    And issues "tsk-a" and "tsk-b" exist
    And issue "tsk-a" has labels "auth"
    When I run "tsk list --label auth"
    Then stdout should contain "tsk-a"
    And stdout should not contain "tsk-b"

  Scenario: List issues sorted by priority
    Given a Taskulus project with default configuration
    And issues "tsk-high" and "tsk-low" exist
    And issue "tsk-high" has priority 1
    And issue "tsk-low" has priority 3
    When I run "tsk list --sort priority"
    Then stdout should list "tsk-high" before "tsk-low"

  Scenario: Full-text search matches title and description
    Given a Taskulus project with default configuration
    And issues "tsk-auth" and "tsk-ui" exist
    And issue "tsk-auth" has title "OAuth setup"
    And issue "tsk-ui" has description "Fix login button"
    When I run "tsk list --search login"
    Then stdout should contain "tsk-ui"
    And stdout should not contain "tsk-auth"

  Scenario: Full-text search matches comments
    Given a Taskulus project with default configuration
    And issues "tsk-note" and "tsk-other" exist
    And the current user is "dev@example.com"
    When I run "tsk comment tsk-note \"Searchable comment\""
    And I run "tsk list --search Searchable"
    Then stdout should contain "tsk-note"
    And stdout should not contain "tsk-other"

  Scenario: Search avoids duplicate results
    Given a Taskulus project with default configuration
    And issues "tsk-dup" and "tsk-other" exist
    And issue "tsk-dup" has title "Dup keyword"
    And the current user is "dev@example.com"
    When I run "tsk comment tsk-dup \"Dup keyword\""
    And I run "tsk list --search Dup"
    Then stdout should contain "tsk-dup" once

  Scenario: Invalid sort key is rejected
    Given a Taskulus project with default configuration
    When I run "tsk list --sort invalid"
    Then the command should fail with exit code 1
    And stderr should contain "invalid sort key"

  Scenario: List fails without a project
    Given an empty git repository
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: List fails outside git repositories
    Given a directory that is not a git repository
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: List fails when dotfile references a missing path
    Given a repository with a .taskulus file referencing a missing path
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "taskulus path not found"

  Scenario: List fails when the daemon returns an error
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And the daemon list request will fail
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "daemon error"

  Scenario: List uses the daemon when enabled
    Given a Taskulus project with default configuration
    And issues "tsk-daemon" exist
    And daemon mode is enabled
    And the daemon is running with a socket
    When I run "tsk list --no-local"
    Then stdout should contain "tsk-daemon"

  Scenario: List fails when local listing raises an error
    Given a Taskulus project with default configuration
    And local listing will fail
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "local listing failed"

  Scenario: List fails when issue files are invalid
    Given a Taskulus project with default configuration
    And issues "tsk-good" and "tsk-better" exist
    And an issue file contains invalid JSON
    And daemon mode is disabled
    When I run "tsk list"
    Then the command should fail with exit code 1

  Scenario: Shared-only listing ignores local issues
    Given a Taskulus project with default configuration
    And issues "tsk-shared" and "tsk-other" exist
    And a local issue "tsk-local" exists
    When shared issues are listed without local issues
    Then the shared-only list should contain "tsk-shared"
    And the shared-only list should not contain "tsk-local"
