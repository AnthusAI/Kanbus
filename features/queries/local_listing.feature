Feature: Local issue listing
  As a Kanbus user
  I want list output to respect local issue filters
  So that I can focus on shared or personal work

  Scenario: List includes local issues by default
    Given a Kanbus project with default configuration
    And an issue "kanbus-shared01" exists
    And a local issue "kanbus-local01" exists
    When I run "kanbus list"
    Then stdout should contain "shared"
    And stdout should contain "local0"

  Scenario: List excludes local issues with --no-local
    Given a Kanbus project with default configuration
    And an issue "kanbus-shared01" exists
    And a local issue "kanbus-local01" exists
    When I run "kanbus list --no-local"
    Then stdout should contain "shared"
    And stdout should not contain "local0"

  Scenario: List shows only local issues with --local-only
    Given a Kanbus project with default configuration
    And an issue "kanbus-shared01" exists
    And a local issue "kanbus-local01" exists
    When I run "kanbus list --local-only"
    Then stdout should contain "local0"
    And stdout should not contain "shared"

  Scenario: Local listing ignores non-issue files
    Given a Kanbus project with default configuration
    And a local issue "kanbus-local01" exists
    And a non-issue file exists in the local issues directory
    When I run "kanbus list --local-only"
    Then stdout should contain "local0"

  Scenario: List rejects local-only conflicts
    Given a Kanbus project with default configuration
    When I run "kanbus list --local-only --no-local"
    Then the command should fail with exit code 1
    And stderr should contain "local-only conflicts with no-local"

  Scenario: Local-only listing fails when local listing raises an error
    Given a Kanbus project with default configuration
    And local listing will fail
    When I run "kanbus list --local-only"
    Then the command should fail with exit code 1
    And stderr should contain "local listing failed"
