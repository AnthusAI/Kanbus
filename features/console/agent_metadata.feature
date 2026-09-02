@console
Feature: Console agent metadata display
  As a Kanbus user
  I want agent metadata visible in the issue detail panel
  So that I can see which AI agent produced an issue or comment

  Scenario: Issue detail shows agent metadata when present
    Given the console is open
    And the console has a task "Add structured logging" with agent platform "cursor" model "composer-2.5"
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then the issue agent metadata should include platform "cursor"
    And the issue agent metadata should include model "composer-2.5"

  Scenario: Issue detail hides agent metadata when absent
    Given the console is open
    And the console has a task "Add structured logging" without agent metadata
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then the issue agent metadata should not be visible

  Scenario: Comment shows agent metadata when present
    Given the console is open
    And the console has a comment from "agent" on task "Fix crash on startup" with agent platform "cursor" model "composer-2.5"
    When I switch to the "Tasks" tab
    And I open the task "Fix crash on startup"
    Then the comment agent metadata should include platform "cursor"

  Scenario: Comment hides agent metadata when absent
    Given the console is open
    And the console has a comment from "Sam" on task "Fix crash on startup"
    When I switch to the "Tasks" tab
    And I open the task "Fix crash on startup"
    Then the comment agent metadata should not be visible
