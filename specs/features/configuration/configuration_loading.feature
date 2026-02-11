@wip
Feature: Configuration loading
  As the Taskulus system
  I need to load and validate project configuration
  So that all operations use consistent type, workflow, and hierarchy rules

  @wip
  Scenario: Load default configuration
    Given a Taskulus project with default configuration
    When the configuration is loaded
    Then the prefix should be "tsk"
    And the hierarchy should be "initiative, epic, task, sub-task"
    And the non-hierarchical types should be "bug, story, chore"
    And the initial status should be "open"
    And the default priority should be 2

  @wip
  Scenario: Reject configuration with unknown fields
    Given a Taskulus project with an invalid configuration containing unknown fields
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  @wip
  Scenario: Reject configuration with empty hierarchy
    Given a Taskulus project with an invalid configuration containing empty hierarchy
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "hierarchy must not be empty"

  @wip
  Scenario: Reject configuration with duplicate type names
    Given a Taskulus project with an invalid configuration containing duplicate types
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "duplicate type name"
