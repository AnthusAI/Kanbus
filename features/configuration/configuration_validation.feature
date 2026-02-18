Feature: Configuration validation
  As a Kanbus maintainer
  I want invalid configurations in .kanbus.yml to be rejected
  So that project rules remain consistent

  Scenario: Unknown configuration fields are rejected
    Given a Kanbus repository with a .kanbus.yml file containing unknown configuration fields
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  Scenario: Configuration must be a mapping
    Given a Kanbus repository with a .kanbus.yml file that is not a mapping
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "configuration must be a mapping"

  Scenario: Empty hierarchy is rejected
    Given a Kanbus repository with a .kanbus.yml file containing an empty hierarchy
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "hierarchy must not be empty"

  Scenario: Duplicate types are rejected
    Given a Kanbus repository with a .kanbus.yml file containing duplicate types
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "duplicate type name"

  Scenario: Missing default workflow is rejected
    Given a Kanbus repository with a .kanbus.yml file missing the default workflow
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default workflow is required"

  Scenario: Missing default priority is rejected
    Given a Kanbus repository with a .kanbus.yml file missing the default priority
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default priority must be in priorities map"

  Scenario: Empty statuses are rejected
    Given a Kanbus repository with a .kanbus.yml file containing empty statuses
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "statuses must not be empty"

  Scenario: Duplicate status names are rejected
    Given a Kanbus repository with a .kanbus.yml file containing duplicate status names
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "duplicate status name"

  Scenario: Workflow statuses must exist in the status list
    Given a Kanbus repository with a .kanbus.yml file containing workflow statuses not in the status list
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "references undefined status"
