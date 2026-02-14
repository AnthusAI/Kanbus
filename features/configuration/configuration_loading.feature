Feature: Configuration loading
  As the Kanbus system
  I need to load and validate project configuration
  So that all operations use consistent type, workflow, and hierarchy rules

  Scenario: Load configuration from .kanbus.yml
    Given a Kanbus repository with a .kanbus.yml file containing the default configuration
    When the configuration is loaded
    Then the project key should be "kanbus"
    And the hierarchy should be "initiative, epic, task, sub-task"
    And the non-hierarchical types should be "bug, story, chore"
    And the initial status should be "open"
    And the default priority should be 2
    And the project directory should be "project"
    And beads compatibility should be false

  Scenario: Load configuration from an empty file
    Given a Kanbus repository with an empty .kanbus.yml file
    When the configuration is loaded
    Then the project key should be "kanbus"
    And the hierarchy should be "initiative, epic, task, sub-task"
    And the non-hierarchical types should be "bug, story, chore"
    And the initial status should be "open"
    And the default priority should be 2
    And the project directory should be "project"

  Scenario: Load configuration from a null file
    Given a Kanbus repository with a .kanbus.yml file containing null
    When the configuration is loaded
    Then the project key should be "kanbus"
    And the hierarchy should be "initiative, epic, task, sub-task"
    And the non-hierarchical types should be "bug, story, chore"
    And the initial status should be "open"
    And the default priority should be 2
    And the project directory should be "project"

  Scenario: Load configuration with custom project directory
    Given a Kanbus repository with a .kanbus.yml file pointing to "tracking" as the project directory
    When the configuration is loaded
    Then the project directory should be "tracking"

  Scenario: Load configuration with absolute project directory
    Given a Kanbus repository with a .kanbus.yml file pointing to an absolute project directory
    When the configuration is loaded
    Then the project directory should match the configured absolute path

  Scenario: Reject configuration with unknown fields
    Given a Kanbus repository with a .kanbus.yml file containing unknown configuration fields
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  Scenario: Reject configuration with empty project directory
    Given a Kanbus repository with a .kanbus.yml file containing an empty project directory
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "project_directory must not be empty"

  Scenario: Reject configuration with empty hierarchy
    Given a Kanbus repository with a .kanbus.yml file containing an empty hierarchy
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "hierarchy must not be empty"

  Scenario: Reject configuration with duplicate type names
    Given a Kanbus repository with a .kanbus.yml file containing duplicate types
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "duplicate type name"

  Scenario: Reject configuration with missing default workflow
    Given a Kanbus repository with a .kanbus.yml file missing the default workflow
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default workflow is required"

  Scenario: Reject configuration with invalid default priority
    Given a Kanbus repository with a .kanbus.yml file missing the default priority
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default priority must be in priorities map"

  Scenario: Reject configuration with invalid field types
    Given a Kanbus repository with a .kanbus.yml file containing wrong field types
    When the configuration is loaded
    Then the command should fail with exit code 1

  Scenario: Reject configuration when file is unreadable
    Given a Kanbus repository with an unreadable .kanbus.yml file
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "Permission denied"

  Scenario: Reject missing configuration file
    Given a Kanbus repository without a .kanbus.yml file
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "configuration file not found"
