Feature: Configuration overrides

  Scenario: Override file replaces configured values
    Given a Taskulus repository with a .taskulus.yml file containing the default configuration
    And the Taskulus configuration sets default assignee "base@example.com"
    And a Taskulus override file sets default assignee "override@example.com"
    When the configuration is loaded
    Then the command should succeed
    And the default assignee should be "override@example.com"

  Scenario: Override file can set time zone
    Given a Taskulus repository with a .taskulus.yml file containing the default configuration
    And a Taskulus override file sets time zone "America/Los_Angeles"
    When the configuration is loaded
    Then the command should succeed
    And the time zone should be "America/Los_Angeles"

  Scenario: Override file can be empty
    Given a Taskulus repository with a .taskulus.yml file containing the default configuration
    And an empty .taskulus.override.yml file
    When the configuration is loaded
    Then the command should succeed
    And the project key should be "tsk"

  Scenario: Override file must be a mapping
    Given a Taskulus repository with a .taskulus.yml file containing the default configuration
    And a Taskulus override file that is not a mapping
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "override configuration must be a mapping"

  Scenario: Override file must be valid YAML
    Given a Taskulus repository with a .taskulus.yml file containing the default configuration
    And a Taskulus override file containing invalid YAML
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "override configuration is invalid"

  Scenario: Override file must be readable
    Given a Taskulus repository with a .taskulus.yml file containing the default configuration
    And an unreadable .taskulus.override.yml file
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "Permission denied"
