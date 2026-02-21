Feature: Jira pull synchronization

  Scenario: Pull issues from Jira into a Kanbus project
    Given a Kanbus project with default configuration
    And a fake Jira server is running with issues:
      | key   | summary              | type | status      | priority |
      | AQ-1  | Build login service  | Task | In Progress | High     |
      | AQ-2  | Fix signup bug       | Bug  | To Do       | Medium   |
    And the Kanbus configuration includes Jira settings pointing at the fake server
    When I run "kanbus jira pull"
    Then the command should succeed
    And stdout should contain "pulled"
    And 2 issue files should exist in the issues directory
    And an issue file with jira_key "AQ-1" should exist with title "Build login service"
    And an issue file with jira_key "AQ-2" should exist with title "Fix signup bug"

  Scenario: Pull is idempotent
    Given a Kanbus project with default configuration
    And a fake Jira server is running with issues:
      | key   | summary              | type | status | priority |
      | AQ-1  | Build login service  | Task | To Do  | Medium   |
    And the Kanbus configuration includes Jira settings pointing at the fake server
    When I run "kanbus jira pull"
    And I run "kanbus jira pull"
    Then the command should succeed
    And stdout should contain "updated"
    And 1 issue files should exist in the issues directory

  Scenario: Dry run does not write files
    Given a Kanbus project with default configuration
    And a fake Jira server is running with issues:
      | key   | summary              | type | status | priority |
      | AQ-1  | Build login service  | Task | To Do  | Medium   |
    And the Kanbus configuration includes Jira settings pointing at the fake server
    When I run "kanbus jira pull --dry-run"
    Then the command should succeed
    And stdout should contain "pulled"
    And 0 issue files should exist in the issues directory

  Scenario: Pull fails when JIRA_API_TOKEN is not set
    Given a Kanbus project with default configuration
    And a fake Jira server is running with issues:
      | key   | summary              | type | status | priority |
      | AQ-1  | Build login service  | Task | To Do  | Medium   |
    And the Kanbus configuration includes Jira settings pointing at the fake server
    And the environment variable "JIRA_API_TOKEN" is unset
    When I run "kanbus jira pull"
    Then the command should fail
    And stderr should contain "JIRA_API_TOKEN"

  Scenario: Pull fails when JIRA_USER_EMAIL is not set
    Given a Kanbus project with default configuration
    And a fake Jira server is running with issues:
      | key   | summary              | type | status | priority |
      | AQ-1  | Build login service  | Task | To Do  | Medium   |
    And the Kanbus configuration includes Jira settings pointing at the fake server
    And the environment variable "JIRA_USER_EMAIL" is unset
    When I run "kanbus jira pull"
    Then the command should fail
    And stderr should contain "JIRA_USER_EMAIL"

  Scenario: Pull fails when no Jira configuration is present
    Given a Kanbus project with default configuration
    When I run "kanbus jira pull"
    Then the command should fail
    And stderr should contain "jira"

  Scenario: Jira issue type is mapped via type_mappings
    Given a Kanbus project with default configuration
    And a fake Jira server is running with issues:
      | key   | summary        | type        | status | priority |
      | AQ-1  | Big initiative | Workstream  | To Do  | Medium   |
    And the Kanbus configuration includes Jira settings pointing at the fake server
    When I run "kanbus jira pull"
    Then the command should succeed
    And an issue file with jira_key "AQ-1" should have type "epic"

  Scenario: Jira parent link is resolved to Kanbus identifier
    Given a Kanbus project with default configuration
    And a fake Jira server is running with issues:
      | key   | summary       | type | status | priority | parent |
      | AQ-1  | Epic work     | Task | To Do  | Medium   |        |
      | AQ-2  | Sub-task work | Task | To Do  | Medium   | AQ-1   |
    And the Kanbus configuration includes Jira settings pointing at the fake server
    When I run "kanbus jira pull"
    Then the command should succeed
    And the issue with jira_key "AQ-2" should have a parent matching the issue with jira_key "AQ-1"

  Scenario: Jira pull loads credentials from .env automatically
    Given a Kanbus project with default configuration
    And a fake Jira server is running with issues:
      | key   | summary              | type | status | priority |
      | AQ-1  | Build login service  | Task | To Do  | Medium   |
      | AQ-2  | Fix signup bug       | Bug  | To Do  | Medium   |
    And the Kanbus configuration includes Jira settings pointing at the fake server
    And credentials are provided via .env file only
    When I run "kanbus jira pull"
    Then the command should succeed
    And stdout should contain "pulled"
    And 2 issue files should exist in the issues directory
