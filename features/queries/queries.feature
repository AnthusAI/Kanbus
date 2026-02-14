Feature: Query and list operations
  As a Taskulus user
  I want to query issues by common fields
  So that I can find the right work quickly

  Scenario: List issues filtered by status
    Given a Taskulus project with default configuration
    And issues "tsk-open" and "tsk-closed" exist
    And issue "tsk-closed" has status "closed"
    When I run "tsk list --status open"
    Then stdout should contain "open"
    And stdout should not contain "closed"

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
    Then stdout should contain "alpha/project T tsk-alphal"
    And stdout should not contain "beta/project T tsk-beta"

  Scenario: List output includes external project paths from configuration file
    Given a repository with a .taskulus.yml file referencing another project
    When I run "tsk list"
    Then stdout should contain the external project path for "tsk-extern"

  Scenario: List issues filtered by type
    Given a Taskulus project with default configuration
    And issues "tsk-task" and "tsk-bug" exist
    And issue "tsk-bug" has type "bug"
    When I run "tsk list --type task"
    Then stdout should contain "task"
    And stdout should not contain "bug"

  Scenario: List issues filtered by assignee
    Given a Taskulus project with default configuration
    And issues "tsk-alpha1" and "tsk-bravo1" exist
    And issue "tsk-alpha1" has assignee "dev@example.com"
    When I run "tsk list --assignee dev@example.com"
    Then stdout should contain "alpha1"
    And stdout should not contain "bravo1"

  Scenario: List issues filtered by label
    Given a Taskulus project with default configuration
    And issues "tsk-alpha1" and "tsk-bravo1" exist
    And issue "tsk-alpha1" has labels "auth"
    When I run "tsk list --label auth"
    Then stdout should contain "alpha1"
    And stdout should not contain "bravo1"

  Scenario: List issues sorted by priority
    Given a Taskulus project with default configuration
    And issues "tsk-high" and "tsk-low" exist
    And issue "tsk-high" has priority 1
    And issue "tsk-low" has priority 3
    When I run "tsk list --sort priority"
    Then stdout should list "high" before "low"

  Scenario: Full-text search matches title and description
    Given a Taskulus project with default configuration
    And issues "tsk-auth" and "tsk-ui" exist
    And issue "tsk-auth" has title "OAuth setup"
    And issue "tsk-ui" has description "Fix login button"
    When I run "tsk list --search login"
    Then stdout should contain "ui"
    And stdout should not contain "auth"

  Scenario: Full-text search matches comments
    Given a Taskulus project with default configuration
    And issues "tsk-note" and "tsk-other" exist
    And the current user is "dev@example.com"
    When I run "tsk comment tsk-note \"Searchable comment\""
    And I run "tsk list --search Searchable"
    Then stdout should contain "note"
    And stdout should not contain "other"

  Scenario: Search avoids duplicate results
    Given a Taskulus project with default configuration
    And issues "tsk-dup" and "tsk-other" exist
    And issue "tsk-dup" has title "Dup keyword"
    And the current user is "dev@example.com"
    When I run "tsk comment tsk-dup \"Dup keyword\""
    And I run "tsk list --search Dup"
    Then stdout should contain "dup" once

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

  Scenario: List fails when repository directory is missing
    Given a repository directory that has been removed
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "No such file or directory"

  Scenario: List fails when repository root is unreadable
    Given a repository directory that is unreadable
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "Permission denied"

  Scenario: List fails when the project directory is unreadable
    Given a Taskulus repository with an unreadable project directory
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "Permission denied"

  Scenario: List tolerates canonicalization failures
    Given a Taskulus project with default configuration
    And an issue "tsk-canon" exists
    And project directory canonicalization will fail
    When I run "tsk list"
    Then stdout should contain "canon"

  Scenario: List fails when configuration path lookup fails
    Given a Taskulus project with default configuration
    And configuration path lookup will fail
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

  Scenario: List formatting fails when configuration path lookup fails after startup
    Given a Taskulus project with default configuration
    And configuration path lookup will fail
    When I list issues directly after configuration path lookup fails
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

  Scenario: Console snapshot fails when configuration is invalid
    Given a Taskulus project with default configuration
    And a Taskulus configuration file that is not a mapping
    When I build a console snapshot directly
    Then the command should fail with exit code 1
    And stderr should contain "configuration must be a mapping"

  Scenario: List fails when dotfile references a missing path
    Given a repository with a .taskulus.yml file referencing a missing path
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "taskulus path not found"

  Scenario: List fails when configuration is invalid
    Given a Taskulus project with an invalid configuration containing unknown fields
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

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
    Then stdout should contain "daemon"

  Scenario: List fails when local listing raises an error
    Given a Taskulus project with default configuration
    And local listing will fail
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "local listing failed"

  Scenario: List fails when configuration path lookup fails
    Given a Taskulus project with default configuration
    And configuration path lookup will fail
    When I run "tsk list"
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

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
