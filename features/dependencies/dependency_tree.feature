Feature: Dependency tree display
  As a Taskulus user
  I want to visualize dependency trees
  So that I can understand blocked work at a glance

  Scenario: ASCII tree display
    Given a Taskulus project with default configuration
    And issues "tsk-root" and "tsk-child" exist
    And issue "tsk-child" depends on "tsk-root" with type "blocked-by"
    And a non-issue file exists in the issues directory
    When I run "tsk dep tree tsk-child"
    Then stdout should contain "tsk-child"
    And stdout should contain "tsk-root"

  Scenario: Dependency tree depth limit
    Given a Taskulus project with default configuration
    And issues "tsk-a" and "tsk-b" exist
    And issues "tsk-b" and "tsk-c" exist
    And issue "tsk-b" depends on "tsk-a" with type "blocked-by"
    And issue "tsk-c" depends on "tsk-b" with type "blocked-by"
    When I run "tsk dep tree tsk-c --depth 1"
    Then stdout should contain "tsk-c"
    And stdout should contain "tsk-b"
    And stdout should not contain "tsk-a"

  Scenario: Large dependency trees summarize output
    Given a Taskulus project with default configuration
    And a dependency tree with more than 25 nodes exists
    When I run "tsk dep tree tsk-root"
    Then stdout should contain "additional nodes omitted"

  Scenario: JSON format output
    Given a Taskulus project with default configuration
    And issues "tsk-root" and "tsk-child" exist
    And issue "tsk-child" depends on "tsk-root" with type "blocked-by"
    When I run "tsk dep tree tsk-child --format json"
    Then stdout should contain "\"id\": \"tsk-child\""
    And stdout should contain "\"dependencies\""

  Scenario: DOT format output
    Given a Taskulus project with default configuration
    And issues "tsk-root" and "tsk-child" exist
    And issue "tsk-child" depends on "tsk-root" with type "blocked-by"
    When I run "tsk dep tree tsk-child --format dot"
    Then stdout should contain "digraph"
    And stdout should contain "\"tsk-child\" -> \"tsk-root\""

  Scenario: Dependency tree fails without a project
    Given an empty git repository
    When I run "tsk dep tree tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Dependency tree fails for missing issue
    Given a Taskulus project with default configuration
    When I run "tsk dep tree tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Dependency tree rejects invalid format
    Given a Taskulus project with default configuration
    And issues "tsk-root" and "tsk-child" exist
    And issue "tsk-child" depends on "tsk-root" with type "blocked-by"
    When I run "tsk dep tree tsk-child --format invalid"
    Then the command should fail with exit code 1
    And stderr should contain "invalid format"

  Scenario: Dependency tree reports missing dependency targets
    Given a Taskulus project with default configuration
    And issue "tsk-child" depends on "tsk-missing" with type "blocked-by"
    When I run "tsk dep tree tsk-child"
    Then the command should fail with exit code 1
    And stderr should contain "dependency target 'tsk-missing' does not exist"

  Scenario: Dependency tree handles cyclic data
    Given a Taskulus project with default configuration
    And issue "tsk-a" depends on "tsk-b" with type "blocked-by"
    And issue "tsk-b" depends on "tsk-a" with type "blocked-by"
    When I run "tsk dep tree tsk-a"
    Then stdout should contain "tsk-a"
    And stdout should contain "tsk-b"
