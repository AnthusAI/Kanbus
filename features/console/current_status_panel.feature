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

  Scenario: Tree toggle shows hierarchical status feed
    Given the console is open
    And no issues exist in the console
    And the console right now configuration has default_tree_expanded true
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Task Gamma" of type "task" under "Epic Beta" updated at "2026-01-03T10:00:00.000Z"
    And I switch to the "Current Status" view
    When I enable the status tree view
    Then the status tree should list issues in order "Initiative Alpha, Epic Beta, Task Gamma"

  Scenario: Tree nodes are collapsible
    Given the console is open
    And no issues exist in the console
    And the console right now configuration has default_tree_expanded true
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Task Gamma" of type "task" under "Epic Beta" updated at "2026-01-03T10:00:00.000Z"
    And I switch to the "Current Status" view
    When I enable the status tree view
    And I collapse the status tree node for "Initiative Alpha"
    Then the status tree should list issues in order "Initiative Alpha"
    When I expand the status tree node for "Initiative Alpha"
    Then the status tree should list issues in order "Initiative Alpha, Epic Beta, Task Gamma"

  Scenario: Tree node default expand reflects configuration
    Given the console is open
    And no issues exist in the console
    And the console right now configuration has default_tree_expanded true
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    And I switch to the "Current Status" view
    When I enable the status tree view
    Then the status tree node for "Initiative Alpha" should be expanded

  Scenario: Tree node default collapse reflects configuration
    Given the console is open
    And no issues exist in the console
    And the console right now configuration has default_tree_expanded false
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    And I switch to the "Current Status" view
    When I enable the status tree view
    Then the status tree node for "Initiative Alpha" should be collapsed

  Scenario: Tree siblings are ordered by updated_at descending
    Given the console is open
    And no issues exist in the console
    And the console right now configuration has default_tree_expanded true
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Task Older" of type "task" under "Epic Beta" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Task Newer" of type "task" under "Epic Beta" updated at "2026-01-04T10:00:00.000Z"
    And I switch to the "Current Status" view
    When I enable the status tree view
    Then the status tree should list issues in order "Initiative Alpha, Epic Beta, Task Newer, Task Older"

  Scenario: Tree node shows issue title and right-now summary
    Given the console is open
    And no issues exist in the console
    And a status hierarchy root "Task Gamma" of type "task" updated at "2026-01-01T10:00:00.000Z"
    And the status issue "Task Gamma" has right-now summary "Working on gamma"
    And I switch to the "Current Status" view
    When I enable the status tree view
    Then the status tree row for "Task Gamma" should show title "Task Gamma"
    And the status tree row for "Task Gamma" should show right-now summary "Working on gamma"

  Scenario: Missing right-now summary shows placeholder in tree
    Given the console is open
    And no issues exist in the console
    And a status hierarchy root "Task Delta" of type "task" updated at "2026-01-01T10:00:00.000Z"
    And I switch to the "Current Status" view
    When I enable the status tree view
    Then the status tree row for "Task Delta" should show right-now summary "(no right-now summary)"

  Scenario: Disabling tree toggle returns to flat feed
    Given the console is open
    And no issues exist in the console
    And a status issue "Older task" updated at "2026-01-01T10:00:00.000Z"
    And a status issue "Newer task" updated at "2026-01-02T10:00:00.000Z"
    And I switch to the "Current Status" view
    When I enable the status tree view
    And I disable the status tree view
    Then the status feed should list issues in order "Newer task, Older task"
