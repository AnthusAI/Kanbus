Feature: Query and list operations
  As a Kanbus user
  I want to query issues by common fields
  So that I can find the right work quickly

  Scenario: List issues filtered by status
    Given a Kanbus project with default configuration
    And issues "kanbus-open" and "kanbus-closed" exist
    And issue "kanbus-closed" has status "closed"
    When I run "kanbus list --status open"
    Then stdout should contain "open"
    And stdout should not contain "closed"

  Scenario: List output includes project paths when multiple projects exist
    Given a repository with multiple projects and issues
    When I run "kanbus list"
    Then stdout should contain "alpha/project T kanbus-alpha"
    And stdout should contain "beta/project T kanbus-beta"

  Scenario: List output includes project paths when multiple projects exist without local issues
    Given a repository with multiple projects and issues
    When I run "kanbus list --no-local"
    Then stdout should contain "alpha/project T kanbus-alpha"
    And stdout should contain "beta/project T kanbus-beta"

  Scenario: List output includes project paths for local-only issues in multi-project repositories
    Given a repository with multiple projects and local issues
    When I run "kanbus list --local-only"
    Then stdout should contain "alpha/project T kanbus-alphal"
    And stdout should not contain "beta/project T kanbus-beta"

  Scenario: List output includes virtual project labels from configuration file
    Given a repository with a .kanbus.yml file with virtual projects configured
    When I run "kanbus list"
    Then stdout should contain the virtual project label for "kanbus-extern"

  Scenario: List issues filtered by type
    Given a Kanbus project with default configuration
    And issues "kanbus-task" and "kanbus-bug" exist
    And issue "kanbus-bug" has type "bug"
    When I run "kanbus list --type task"
    Then stdout should contain "task"
    And stdout should not contain "bug"

  Scenario: List issues filtered by assignee
    Given a Kanbus project with default configuration
    And issues "kanbus-alpha1" and "kanbus-bravo1" exist
    And issue "kanbus-alpha1" has assignee "dev@example.com"
    When I run "kanbus list --assignee dev@example.com"
    Then stdout should contain "alpha1"
    And stdout should not contain "bravo1"

  Scenario: List issues filtered by label
    Given a Kanbus project with default configuration
    And issues "kanbus-alpha1" and "kanbus-bravo1" exist
    And issue "kanbus-alpha1" has labels "auth"
    When I run "kanbus list --label auth"
    Then stdout should contain "alpha1"
    And stdout should not contain "bravo1"

  Scenario: List issues sorted by priority
    Given a Kanbus project with default configuration
    And issues "kanbus-high" and "kanbus-low" exist
    And issue "kanbus-high" has priority 1
    And issue "kanbus-low" has priority 3
    When I run "kanbus list --sort priority"
    Then stdout should list "high" before "low"

  Scenario: Full-text search matches title and description
    Given a Kanbus project with default configuration
    And issues "kanbus-auth" and "kanbus-ui" exist
    And issue "kanbus-auth" has title "OAuth setup"
    And issue "kanbus-ui" has description "Fix login button"
    When I run "kanbus list --search login"
    Then stdout should contain "ui"
    And stdout should not contain "auth"

  Scenario: Full-text search matches comments
    Given a Kanbus project with default configuration
    And issues "kanbus-note" and "kanbus-other" exist
    And the current user is "dev@example.com"
    When I run "kanbus comment kanbus-note \"Searchable comment\""
    And I run "kanbus list --search Searchable"
    Then stdout should contain "note"
    And stdout should not contain "other"

  Scenario: Search avoids duplicate results
    Given a Kanbus project with default configuration
    And issues "kanbus-dup" and "kanbus-other" exist
    And issue "kanbus-dup" has title "Dup keyword"
    And the current user is "dev@example.com"
    When I run "kanbus comment kanbus-dup \"Dup keyword\""
    And I run "kanbus list --search Dup"
    Then stdout should contain "dup" once

  Scenario: Invalid sort key is rejected
    Given a Kanbus project with default configuration
    When I run "kanbus list --sort invalid"
    Then the command should fail with exit code 1
    And stderr should contain "invalid sort key"

  Scenario: List fails without a project
    Given an empty git repository
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: List fails outside git repositories
    Given a directory that is not a git repository
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: List fails when repository directory is missing
    Given a repository directory that has been removed
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "No such file or directory"

  Scenario: List fails when repository root is unreadable
    Given a repository directory that is unreadable
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "Permission denied"

  Scenario: List fails when the project directory is unreadable
    Given a Kanbus repository with an unreadable project directory
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "Permission denied"

  Scenario: List tolerates canonicalization failures
    Given a Kanbus project with default configuration
    And an issue "kanbus-canon" exists
    And project directory canonicalization will fail
    When I run "kanbus list"
    Then stdout should contain "canon"

  Scenario: List fails when configuration path lookup fails
    Given a Kanbus project with default configuration
    And configuration path lookup will fail
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

  Scenario: List formatting fails when configuration path lookup fails after startup
    Given a Kanbus project with default configuration
    And configuration path lookup will fail
    When I list issues directly after configuration path lookup fails
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

  Scenario: Console snapshot fails when configuration is invalid
    Given a Kanbus project with default configuration
    And a Kanbus configuration file that is not a mapping
    When I build a console snapshot directly
    Then the command should fail with exit code 1
    And stderr should contain "configuration must be a mapping"

  Scenario: List fails when dotfile references a missing path
    Given a repository with a .kanbus.yml file referencing a missing path
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "virtual project path not found"

  Scenario: List fails when configuration is invalid
    Given a Kanbus project with an invalid configuration containing unknown fields
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  Scenario: List fails when the daemon returns an error
    Given a Kanbus project with default configuration
    And daemon mode is enabled
    And the daemon list request will fail
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "daemon error"

  Scenario: List uses the daemon when enabled
    Given a Kanbus project with default configuration
    And issues "kanbus-daemon" exist
    And daemon mode is enabled
    And the daemon is running with a socket
    When I run "kanbus list --no-local"
    Then stdout should contain "daemon"

  Scenario: List fails when local listing raises an error
    Given a Kanbus project with default configuration
    And local listing will fail
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "local listing failed"

  Scenario: List fails when configuration path lookup fails
    Given a Kanbus project with default configuration
    And configuration path lookup will fail
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

  Scenario: List fails when issue files are invalid
    Given a Kanbus project with default configuration
    And issues "kanbus-good" and "kanbus-better" exist
    And an issue file contains invalid JSON
    And daemon mode is disabled
    When I run "kanbus list"
    Then the command should fail with exit code 1

  Scenario: Shared-only listing ignores local issues
    Given a Kanbus project with default configuration
    And issues "kanbus-shared" and "kanbus-other" exist
    And a local issue "kanbus-local" exists
    When shared issues are listed without local issues
    Then the shared-only list should contain "kanbus-shared"
    And the shared-only list should not contain "kanbus-local"
