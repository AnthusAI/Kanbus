@wip
Feature: Maintenance commands
  As a Taskulus maintainer
  I want diagnostic and maintenance commands
  So that the repository stays healthy

  @wip
  Scenario: Validate project integrity
    Given a Taskulus project with default configuration
    When I run "tsk validate"
    Then the command should succeed

  @wip
  Scenario: Report project statistics
    Given a Taskulus project with default configuration
    And issues "tsk-open" and "tsk-closed" exist
    And issue "tsk-closed" has status "closed"
    When I run "tsk stats"
    Then stdout should contain "total issues"
    And stdout should contain "open issues"
    And stdout should contain "closed issues"

  @wip
  Scenario: Stats include type counts
    Given a Taskulus project with default configuration
    And issues "tsk-task" and "tsk-bug" exist
    And issue "tsk-bug" has type "bug"
    When I run "tsk stats"
    Then stdout should contain "type: task"
    And stdout should contain "type: bug"
