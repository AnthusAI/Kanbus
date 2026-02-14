Feature: Configuration standardization across Python and Rust
  As Kanbus maintainers
  We need a single configuration model and loader behavior
  So both implementations enforce the same rules without fallbacks

  @wip
  Scenario: Load configuration from the default file
    Given a Kanbus project with a file "kanbus.yml" containing a valid configuration
    And the environment variable KANBUS_PROJECT_KEY is not set
    When I load the configuration
    Then the project key should be "KAN"
    And the hierarchy should be "initiative > epic > issue > subtask"
    And the default priority should be "medium"

  @wip
  Scenario: Missing configuration file fails
    Given no "kanbus.yml" file exists
    When I load the configuration
    Then the command should fail with exit code 1
    And stderr should contain "kanbus.yml not found"

  @wip
  Scenario: Unknown configuration field is rejected
    Given a Kanbus project with a file "kanbus.yml" containing an unknown top-level field
    When I load the configuration
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  @wip
  Scenario: Hierarchy is fixed and cannot be customized
    Given a Kanbus project with a file "kanbus.yml" attempting to override the hierarchy
    When I load the configuration
    Then the command should fail with exit code 1
    And stderr should contain "hierarchy is fixed"

  @wip
  Scenario: Each issue type must bind to a workflow
    Given a Kanbus project with a file "kanbus.yml" where issue type "bug" has no workflow binding
    When I load the configuration
    Then the command should fail with exit code 1
    And stderr should contain "missing workflow binding for issue type"

  @wip
  Scenario: Invalid status transition is rejected
    Given a Kanbus project with default workflows
    And an issue "kanbus-123" of type "bug" with status "open"
    When I update issue "kanbus-123" to status "blocked"
    Then the command should fail with exit code 1
    And stderr should contain "invalid transition"

  @wip
  Scenario: Accept external priorities on import but enforce canonical on update
    Given a Kanbus project with canonical priorities "critical, high, medium, low"
    And priority_import_aliases mapping P0->critical, P1->high, P2->medium, P3->low
    And an imported issue exists with priority "P0"
    When I save the issue through Kanbus
    Then the stored priority should be "critical"
    And when I attempt to update an issue to priority "custom"
    Then the command should fail with exit code 1
    And stderr should contain "invalid priority"

  @wip
  Scenario: Dotenv and env precedence match Python dotyaml
    Given a ".env" file that sets KANBUS_PROJECT_KEY to "ENV"
    And a "kanbus.yml" that sets project_key to "YAML"
    And the environment variable KANBUS_PROJECT_KEY is not set
    When I load the configuration without override
    Then the project key should be "ENV"
    When I load the configuration with override enabled
    Then the project key should be "YAML"
