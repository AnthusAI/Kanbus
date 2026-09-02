@console
Feature: Console current status panel
  As a Kanbus user
  I want a current status feed in the web console
  So that I can review recently-updated issues and their right-now summaries

  Scenario: Current status panel is selectable alongside board metrics and wiki
    Given the console is open
    When I switch to the "Current Status" view
    Then the current status view should be active
    And the board view should be inactive

  Scenario: Selecting current status shows reverse-chronological feed
    Given the console is open
    And no issues exist in the console
    And a status issue "Older task" updated at "2026-01-01T10:00:00.000Z"
    And a status issue "Newer task" updated at "2026-01-02T10:00:00.000Z"
    When I switch to the "Current Status" view
    Then the status feed should list issues in order "Newer task, Older task"

  Scenario: Feed row shows issue title and right-now summary
    Given the console is open
    And no issues exist in the console
    And a status issue "Alpha task" updated at "2026-01-01T10:00:00.000Z"
    And the status issue "Alpha task" has right-now summary "Working on alpha"
    When I switch to the "Current Status" view
    Then the status feed row for "Alpha task" should show title "Alpha task"
    And the status feed row for "Alpha task" should show right-now summary "Working on alpha"

  Scenario: Missing right-now summary shows placeholder
    Given the console is open
    And no issues exist in the console
    And a status issue "Beta task" updated at "2026-01-01T10:00:00.000Z"
    When I switch to the "Current Status" view
    Then the status feed row for "Beta task" should show right-now summary "(no right-now summary)"

  Scenario: Live update refreshes feed row
    Given the console is open
    And no issues exist in the console
    And a status issue "Gamma task" updated at "2026-01-01T10:00:00.000Z"
    And the status issue "Gamma task" has right-now summary "Initial summary"
    And I switch to the "Current Status" view
    When the right-now summary for "Gamma task" is updated to "Updated summary"
    Then the status feed row for "Gamma task" should show right-now summary "Updated summary"

  Scenario: Feed is limited to the most recent issues
    Given the console is open
    And no issues exist in the console
    And 35 status issues exist with sequential update times
    When I switch to the "Current Status" view
    Then the status feed should contain 30 rows

  @console-server
  Scenario: Realtime issue update refreshes current status feed row
    Given the console is open
    And a Kanbus project with default configuration
    And no issues exist in the console
    And a status issue "Live task" updated at "2026-01-01T10:00:00.000Z"
    And the status issue "Live task" has right-now summary "Before update"
    And the console server is running

    And I switch to the "Current Status" view
    When the console receives an issue update for "Live task" with right-now summary "After update"
    Then the status feed row for "Live task" should show right-now summary "After update"
