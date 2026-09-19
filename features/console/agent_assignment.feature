@console
Feature: Console agent assignment display
  As a Kanbus user
  I want routing assignment separate from provenance
  So that I can see how an issue will be executed

  Scenario: Detail view shows effective class assignment
    Given the console is open
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then the issue agent assignment should show route "Class · implementation"
    And the issue agent assignment should show effective "gpt-5.6-luna"

  Scenario: Detail view shows an unassigned issue
    Given the console is open
    And the console has a task "Add structured logging" without agent assignment
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then the issue agent assignment should show unassigned
