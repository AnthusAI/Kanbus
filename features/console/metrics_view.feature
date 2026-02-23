Feature: Console metrics view
  As a Kanbus user
  I want a metrics view
  So that I can review counts and charts for the current filters

  Scenario: Default view is board
    Given the console is open
    And local storage is cleared
    When the console is reloaded
    Then the board view should be active
    And the metrics view should be inactive
    And the metrics toggle should select "Board"

  Scenario: Switching to metrics view
    Given the console is open
    When I switch to the "Metrics" view
    Then the metrics view should be active
    And the board view should be inactive
    And the metrics toggle should select "Metrics"

  Scenario: Switching back to board view
    Given the console is open
    And I switch to the "Metrics" view
    When I switch to the "Board" view
    Then the board view should be active
    And the metrics view should be inactive
    And the metrics toggle should select "Board"

  Scenario: View toggle uses board and metrics icons
    Given the console is open
    Then the metrics toggle should include a board icon
    And the metrics toggle should include a chart icon

  Scenario: View selection persists across reload
    Given the console is open
    When I switch to the "Metrics" view
    And the console is reloaded
    Then the metrics view should be active
    And the metrics toggle should select "Metrics"

  Scenario: Metrics summary counts reflect issues
    Given the console is open
    And a metrics issue "Alpha epic" of type "epic" with status "open" in project "kbs" from "shared"
    And a metrics issue "Beta epic" of type "epic" with status "in_progress" in project "kbs" from "shared"
    And a metrics issue "Done task" of type "task" with status "closed" in project "kbs" from "local"
    When I switch to the "Metrics" view
    Then the metrics total should be "3"
    And the metrics status count for "open" should be "1"
    And the metrics status count for "in_progress" should be "1"
    And the metrics status count for "closed" should be "1"

  Scenario: Metrics summary shows project and scope breakdowns when available
    Given the console is open with virtual projects configured
    And a metrics issue "Alpha epic" of type "epic" with status "open" in project "alpha" from "shared"
    And a metrics issue "Beta epic" of type "epic" with status "open" in project "beta" from "shared"
    And a metrics issue "Local task" of type "task" with status "closed" in project "kbs" from "local"
    When I switch to the "Metrics" view
    Then the metrics project count for "alpha" should be "1"
    And the metrics project count for "beta" should be "1"
    And the metrics project count for "kbs" should be "1"
    And the metrics scope count for "Project" should be "2"
    And the metrics scope count for "Local" should be "1"

  Scenario: Chart groups by issue type and uses status colors
    Given the console is open
    And a metrics issue "Alpha epic" of type "epic" with status "open" in project "kbs" from "shared"
    And a metrics issue "Beta epic" of type "epic" with status "closed" in project "kbs" from "shared"
    And a metrics issue "Task one" of type "task" with status "in_progress" in project "kbs" from "shared"
    When I switch to the "Metrics" view
    Then the metrics chart should include type "epic"
    And the metrics chart should include type "task"
    And the metrics chart should stack statuses for "epic"
    And the metrics chart should include a legend
    And the metrics chart should use category colors

  Scenario: Chart reflects active filters
    Given the console is open
    And a metrics issue "Alpha epic" of type "epic" with status "open" in project "alpha" from "shared"
    And a metrics issue "Beta epic" of type "epic" with status "open" in project "beta" from "shared"
    When I select metrics project "alpha"
    And I switch to the "Metrics" view
    Then the metrics total should be "1"
    And the metrics chart should include type "epic"
