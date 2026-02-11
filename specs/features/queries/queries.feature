@wip
Feature: Query and list operations
  As a Taskulus user
  I want to query issues by common fields
  So that I can find the right work quickly

  @wip
  Scenario: List issues filtered by status
    Given a Taskulus project with default configuration
    And issues "tsk-open" and "tsk-closed" exist
    And issue "tsk-closed" has status "closed"
    When I run "tsk list --status open"
    Then stdout should contain "tsk-open"
    And stdout should not contain "tsk-closed"

  @wip
  Scenario: List issues filtered by type
    Given a Taskulus project with default configuration
    And issues "tsk-task" and "tsk-bug" exist
    And issue "tsk-bug" has type "bug"
    When I run "tsk list --type task"
    Then stdout should contain "tsk-task"
    And stdout should not contain "tsk-bug"

  @wip
  Scenario: List issues filtered by assignee
    Given a Taskulus project with default configuration
    And issues "tsk-a" and "tsk-b" exist
    And issue "tsk-a" has assignee "dev@example.com"
    When I run "tsk list --assignee dev@example.com"
    Then stdout should contain "tsk-a"
    And stdout should not contain "tsk-b"

  @wip
  Scenario: List issues filtered by label
    Given a Taskulus project with default configuration
    And issues "tsk-a" and "tsk-b" exist
    And issue "tsk-a" has labels "auth"
    When I run "tsk list --label auth"
    Then stdout should contain "tsk-a"
    And stdout should not contain "tsk-b"

  @wip
  Scenario: List issues sorted by priority
    Given a Taskulus project with default configuration
    And issues "tsk-high" and "tsk-low" exist
    And issue "tsk-high" has priority 1
    And issue "tsk-low" has priority 3
    When I run "tsk list --sort priority"
    Then stdout should list "tsk-high" before "tsk-low"

  @wip
  Scenario: Full-text search matches title and description
    Given a Taskulus project with default configuration
    And issues "tsk-auth" and "tsk-ui" exist
    And issue "tsk-auth" has title "OAuth setup"
    And issue "tsk-ui" has description "Fix login button"
    When I run "tsk list --search login"
    Then stdout should contain "tsk-ui"
    And stdout should not contain "tsk-auth"
