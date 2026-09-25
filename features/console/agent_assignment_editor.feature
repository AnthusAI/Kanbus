@console @kbs-daf353
Feature: Console routing assignment editor
  As a Kanbus user
  I want to choose an issue's routing assignment from the issue detail view
  So that I control which agent works on it without editing labels

  Background:
    Given the console is open
    And the console has only these issues:
      | id            | title          | status      |
      | kbs-assign    | Assign me      | open        |
      | kbs-running   | Running issue  | in_progress |
    And the Kanbus configuration has a router with class "implementation" using provider "codex-default"
    And the issue "kbs-running" has labels "agent-class:implementation"
    And the console page is reloaded

  Scenario: Choosing a class from the detail view
    When I switch to the "Tasks" tab
    And I open the task "Assign me"
    And I choose the routing assignment "Class · implementation"
    And I save the routing assignment
    Then the routing assignment should be saved
    And the routing assignment should read "Class · implementation"

  Scenario: Clearing an assignment from the detail view
    When I switch to the "Tasks" tab
    And I open the task "Assign me"
    And I choose the routing assignment "Provider · codex-default"
    And I save the routing assignment
    And I choose the routing assignment "Unassigned"
    And I save the routing assignment
    Then the routing assignment should read "Unassigned"

  Scenario: The editor is locked while the router runs the issue
    When I switch to the "Tasks" tab
    And I open the task "Running issue"
    Then the routing assignment editor should be locked
