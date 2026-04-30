@rust-only
Feature: Kanbus orchestration

  Scenario: Claiming the next ready issue emits JSON
    Given a Kanbus project with default configuration
    And an issue "kanbus-ready01" of type "task" with status "open"
    And an issue "kanbus-ready02" of type "task" with status "open"
    When I run "kanbus claim-next --ready --assignee worker-one --json"
    Then the command should succeed
    And stdout should contain "\"id\""
    And stdout should contain "\"assignee\""
    And stdout should contain "\"worker-one\""

  Scenario: Runs can be recorded and inspected
    Given a Kanbus project with default configuration
    And an issue "kanbus-run01" of type "task" with status "open"
    When I run "kanbus runs create kanbus-run01 --worker worker-one --json"
    Then the command should succeed
    And stdout should contain "\"run_id\""
    And stdout should contain "\"kanbus-run-"
    And stdout should contain "\"issue_id\""
    And stdout should contain "\"kanbus-run01\""
    When I run "kanbus runs list --json"
    Then the command should succeed
    And stdout should contain "\"kanbus-run01\""
