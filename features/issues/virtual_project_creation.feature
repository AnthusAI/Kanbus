Feature: Issue creation with virtual projects
  As a Kanbus user with virtual projects
  I want to control where new issues are created
  So that issues land in the correct project

  Scenario: New issues go to current project by default
    Given a Kanbus project with virtual projects configured
    When I run "kanbus create New task for the board"
    Then the command should succeed
    And an issue file should be created in the current project issues directory
    And no issue file should be created in any virtual project

  Scenario: New issue project can be configured to a virtual project
    Given a Kanbus project with new_issue_project set to "alpha"
    When I run "kanbus create Task for alpha project"
    Then the command should succeed
    And an issue file should be created in the "alpha" project issues directory

  Scenario: New issue project set to ask prompts the user
    Given a Kanbus project with new_issue_project set to "ask"
    When I run "kanbus create Interactive task" interactively
    And I select "alpha" from the project prompt
    Then the command should succeed
    And an issue file should be created in the "alpha" project issues directory

  Scenario: New issue project ask lists all available projects
    Given a Kanbus project with new_issue_project set to "ask"
    And virtual projects "alpha" and "beta" are configured
    When I run "kanbus create Interactive task" interactively
    Then the project prompt should list "kbs"
    And the project prompt should list "alpha"
    And the project prompt should list "beta"

  Scenario: Local flag still routes to current project local directory
    Given a Kanbus project with new_issue_project set to "alpha"
    When I run "kanbus create --local Local task"
    Then the command should succeed
    And a local issue file should be created in the current project local directory

  Scenario: Explicit project flag overrides new_issue_project config
    Given a Kanbus project with new_issue_project set to "alpha"
    When I run "kanbus create --project beta Task for beta"
    Then the command should succeed
    And an issue file should be created in the "beta" project issues directory

  Scenario: Invalid new_issue_project config is rejected
    Given a Kanbus project with new_issue_project set to "nonexistent"
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "new_issue_project references unknown project"

  Scenario: Local flag with explicit project creates in that project local directory
    Given a Kanbus project with virtual projects configured
    When I run "kanbus create --local --project alpha Local alpha task"
    Then the command should succeed
    And a local issue file should be created in the "alpha" project local directory
