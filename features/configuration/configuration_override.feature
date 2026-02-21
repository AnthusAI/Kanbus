Feature: Configuration overrides

  Scenario: Override file replaces configured values
    Given a Kanbus repository with a .kanbus.yml file containing the default configuration
    And the Kanbus configuration sets default assignee "base@example.com"
    And a Kanbus override file sets default assignee "override@example.com"
    When the configuration is loaded
    Then the command should succeed
    And the default assignee should be "override@example.com"

  Scenario: Override file can set time zone
    Given a Kanbus repository with a .kanbus.yml file containing the default configuration
    And a Kanbus override file sets time zone "America/Los_Angeles"
    When the configuration is loaded
    Then the command should succeed
    And the time zone should be "America/Los_Angeles"

  Scenario: Override file can be empty
    Given a Kanbus repository with a .kanbus.yml file containing the default configuration
    And an empty .kanbus.override.yml file
    When the configuration is loaded
    Then the command should succeed
    And the project key should be "kanbus"

  Scenario: Override file must be a mapping
    Given a Kanbus repository with a .kanbus.yml file containing the default configuration
    And a Kanbus override file that is not a mapping
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "override configuration must be a mapping"

  Scenario: Override file must be valid YAML
    Given a Kanbus repository with a .kanbus.yml file containing the default configuration
    And a Kanbus override file containing invalid YAML
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "override configuration is invalid"

  Scenario: Override file merges virtual_projects additively
    Given a Kanbus repository with a .kanbus.yml file containing the default configuration
    And the Kanbus configuration has a virtual project "alpha" at path "../Alpha/project"
    And a Kanbus override file adds a virtual project "beta" at path "../Beta/project"
    When the configuration is loaded
    Then the command should succeed
    And the configuration should have virtual project "alpha"
    And the configuration should have virtual project "beta"

  Scenario: Override file must be readable
    Given a Kanbus repository with a .kanbus.yml file containing the default configuration
    And an unreadable .kanbus.override.yml file
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "Permission denied"
