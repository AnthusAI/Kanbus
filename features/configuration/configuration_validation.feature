Feature: Configuration validation
  As a Taskulus maintainer
  I want invalid configurations in .taskulus.yml to be rejected
  So that project rules remain consistent

  Scenario: Unknown configuration fields are rejected
    Given a Taskulus repository with a .taskulus.yml file containing unknown configuration fields
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  Scenario: Configuration must be a mapping
    Given a Taskulus repository with a .taskulus.yml file that is not a mapping
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "configuration must be a mapping"

  Scenario: Empty hierarchy is rejected
    Given a Taskulus repository with a .taskulus.yml file containing an empty hierarchy
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "hierarchy must not be empty"

  Scenario: Duplicate types are rejected
    Given a Taskulus repository with a .taskulus.yml file containing duplicate types
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "duplicate type name"

  Scenario: Missing default workflow is rejected
    Given a Taskulus repository with a .taskulus.yml file missing the default workflow
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default workflow is required"

  Scenario: Missing default priority is rejected
    Given a Taskulus repository with a .taskulus.yml file missing the default priority
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default priority must be in priorities map"
