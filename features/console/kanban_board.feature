@console
Feature: Console kanban board
  As a Kanbus user
  I want a realtime kanban console for issues
  So that I can track work visually

  Scenario: Default view shows epics when no preference is stored
    Given the console is open
    And local storage is cleared
    When the console is reloaded
    Then the "Epics" tab should be selected
    And I should see the issue "Observability overhaul"
    And I should not see the issue "Increase reliability"

  Scenario: Initiatives tab shows initiative issues
    Given the console is open
    When I switch to the "Initiatives" tab
    Then I should see the issue "Increase reliability"

  Scenario: Tasks tab shows task level issues
    Given the console is open
    When I switch to the "Tasks" tab
    Then I should see the issue "Add structured logging"
    And I should see the issue "Fix crash on startup"
    And I should not see the issue "Wire logger middleware"

  Scenario: Task detail shows sub-tasks
    Given the console is open
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then I should see the sub-task "Wire logger middleware"

  Scenario: Realtime updates surface new tasks
    Given the console is open
    When I switch to the "Tasks" tab
    And a new task issue named "Ship trace headers" is added
    Then I should see the issue "Ship trace headers"

  Scenario: View mode preference is remembered
    Given the console is open
    When I switch to the "Tasks" tab
    And the console is reloaded
    Then the "Tasks" tab should be selected
