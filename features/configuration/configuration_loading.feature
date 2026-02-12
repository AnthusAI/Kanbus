Feature: Configuration loading
  As the Taskulus system
  I need to load and validate project configuration
  So that all operations use consistent type, workflow, and hierarchy rules

  Scenario: Load default configuration
    Given a Taskulus project with default configuration
    When the configuration is loaded
    Then the prefix should be "tsk"
    And the hierarchy should be "initiative, epic, task, sub-task"
    And the non-hierarchical types should be "bug, story, chore"
    And the initial status should be "open"
    And the default priority should be 2

  Scenario: Load configuration from file
    Given a Taskulus project with a configuration file
    When the configuration is loaded
    Then the prefix should be "tsk"

  Scenario: Reject configuration with unknown fields
    Given a Taskulus project with an invalid configuration containing unknown fields
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  Scenario: Reject configuration with empty hierarchy
    Given a Taskulus project with an invalid configuration containing empty hierarchy
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "hierarchy must not be empty"

  Scenario: Reject configuration with duplicate type names
    Given a Taskulus project with an invalid configuration containing duplicate types
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "duplicate type name"

  Scenario: Reject configuration with missing default workflow
    Given a Taskulus project with an invalid configuration missing the default workflow
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default workflow is required"

  Scenario: Reject configuration with invalid default priority
    Given a Taskulus project with an invalid configuration missing the default priority
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default priority must be in priorities map"

  Scenario: Reject configuration with invalid field types
    Given a Taskulus project with an invalid configuration containing wrong field types
    When the configuration is loaded
    Then the command should fail with exit code 1

  Scenario: Reject configuration when file is unreadable
    Given a Taskulus project with an unreadable configuration file
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "Permission denied"
