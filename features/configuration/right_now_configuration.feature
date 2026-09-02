Feature: Right now configuration
  As a Kanbus administrator
  I want to configure right-now summary behavior in kanbus.yml
  So that the console can show concise issue summaries

  Scenario: Right now configuration loads with defaults when absent
    Given a Kanbus repository with a .kanbus.yml file containing the default configuration
    When the configuration is loaded
    Then the command should succeed
    And the right now configuration should have enabled true
    And the right now configuration should have default_tree_expanded false
    And the right now configuration should have max_length 120
    And the right now model override should be unset

  Scenario: Right now configuration loads explicit values
    Given a Kanbus project with a file "kanbus.yml" containing:
      """
      right_now:
        enabled: false
        default_tree_expanded: true
        max_length: 80
        model: "gpt-4o-mini"
      """
    When I load the configuration
    Then the command should succeed
    And the right now configuration should have enabled false
    And the right now configuration should have default_tree_expanded true
    And the right now configuration should have max_length 80
    And the right now model override should be "gpt-4o-mini"

  Scenario: Right now max_length must be greater than zero
    Given a Kanbus project with a file "kanbus.yml" containing:
      """
      right_now:
        max_length: 0
      """
    When I load the configuration
    Then the command should fail with exit code 1
    And stderr should contain "right_now.max_length must be greater than 0"

  Scenario: Unknown right now configuration fields are rejected
    Given a Kanbus project with a file "kanbus.yml" containing:
      """
      right_now:
        unknown_field: "value"
      """
    When I load the configuration
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"
