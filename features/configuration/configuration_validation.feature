Feature: Configuration validation
  As a Taskulus maintainer
  I want invalid configurations to be rejected
  So that project rules remain consistent

  Scenario: Unknown configuration fields are rejected
    Given a Taskulus project with an invalid configuration containing unknown fields
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  Scenario: Empty hierarchy is rejected
    Given a Taskulus project with an invalid configuration containing empty hierarchy
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "hierarchy must not be empty"

  Scenario: Duplicate types are rejected
    Given a Taskulus project with an invalid configuration containing duplicate types
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "duplicate type name"

  Scenario: Missing default workflow is rejected
    Given a Taskulus project with an invalid configuration missing the default workflow
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default workflow is required"

  Scenario: Missing default priority is rejected
    Given a Taskulus project with an invalid configuration missing the default priority
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "default priority must be in priorities map"
