@console
Feature: Console route navigation

  Scenario: Direct epics route selects epics tab
    Given the console is open
    When I open the console route "/epics/"
    Then the "Epics" tab should be selected

  Scenario: Direct issues route selects issues tab
    Given the console is open
    When I open the console route "/issues/"
    Then the "Issues" tab should be selected

  Scenario: Direct issue route selects tab by issue type
    Given the console is open
    When I open the console route "/issues/kanbus-epic-1"
    Then the "Epics" tab should be selected
    And the detail panel should show issue "Observability overhaul"

  Scenario: Context route leaves view tab unselected
    Given the console is open
    When I open the console route "/issues/kanbus-epic-1/kanbus-task-1"
    Then no view tab should be selected
    And the detail panel should show issue "Add structured logging"

  Scenario: Parent-all route scopes to descendants
    Given the console is open
    When I open the console route "/issues/kanbus-epic-1/all"
    Then no view tab should be selected

  Scenario: Short id route resolves issue
    Given the console is open
    When I open the console route "/issues/kanbus-epic"
    Then the "Epics" tab should be selected
    And the detail panel should show issue "Observability overhaul"
