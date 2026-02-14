Feature: Dependency tree display
  As a Kanbus user
  I want to visualize dependency trees
  So that I can understand blocked work at a glance

  Scenario: ASCII tree display
    Given a Kanbus project with default configuration
    And issues "kanbus-root" and "kanbus-child" exist
    And issue "kanbus-child" depends on "kanbus-root" with type "blocked-by"
    And a non-issue file exists in the issues directory
    When I run "kanbus dep tree kanbus-child"
    Then stdout should contain "kanbus-child"
    And stdout should contain "kanbus-root"

  Scenario: Dependency tree depth limit
    Given a Kanbus project with default configuration
    And issues "kanbus-a" and "kanbus-b" exist
    And issues "kanbus-b" and "kanbus-c" exist
    And issue "kanbus-b" depends on "kanbus-a" with type "blocked-by"
    And issue "kanbus-c" depends on "kanbus-b" with type "blocked-by"
    When I run "kanbus dep tree kanbus-c --depth 1"
    Then stdout should contain "kanbus-c"
    And stdout should contain "kanbus-b"
    And stdout should not contain "kanbus-a"

  Scenario: Large dependency trees summarize output
    Given a Kanbus project with default configuration
    And a dependency tree with more than 25 nodes exists
    When I run "kanbus dep tree kanbus-root"
    Then stdout should contain "additional nodes omitted"

  Scenario: JSON format output
    Given a Kanbus project with default configuration
    And issues "kanbus-root" and "kanbus-child" exist
    And issue "kanbus-child" depends on "kanbus-root" with type "blocked-by"
    When I run "kanbus dep tree kanbus-child --format json"
    Then stdout should contain "\"id\": \"kanbus-child\""
    And stdout should contain "\"dependencies\""

  Scenario: DOT format output
    Given a Kanbus project with default configuration
    And issues "kanbus-root" and "kanbus-child" exist
    And issue "kanbus-child" depends on "kanbus-root" with type "blocked-by"
    When I run "kanbus dep tree kanbus-child --format dot"
    Then stdout should contain "digraph"
    And stdout should contain "\"kanbus-child\" -> \"kanbus-root\""

  Scenario: Dependency tree fails without a project
    Given an empty git repository
    When I run "kanbus dep tree kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Dependency tree fails for missing issue
    Given a Kanbus project with default configuration
    When I run "kanbus dep tree kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Dependency tree rejects invalid format
    Given a Kanbus project with default configuration
    And issues "kanbus-root" and "kanbus-child" exist
    And issue "kanbus-child" depends on "kanbus-root" with type "blocked-by"
    When I run "kanbus dep tree kanbus-child --format invalid"
    Then the command should fail with exit code 1
    And stderr should contain "invalid format"

  Scenario: Dependency tree reports missing dependency targets
    Given a Kanbus project with default configuration
    And issue "kanbus-child" depends on "kanbus-missing" with type "blocked-by"
    When I run "kanbus dep tree kanbus-child"
    Then the command should fail with exit code 1
    And stderr should contain "dependency target 'kanbus-missing' does not exist"

  Scenario: Dependency tree handles cyclic data
    Given a Kanbus project with default configuration
    And issue "kanbus-a" depends on "kanbus-b" with type "blocked-by"
    And issue "kanbus-b" depends on "kanbus-a" with type "blocked-by"
    When I run "kanbus dep tree kanbus-a"
    Then stdout should contain "kanbus-a"
    And stdout should contain "kanbus-b"
