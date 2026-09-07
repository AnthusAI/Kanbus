@console
Feature: Console current status panel
  As a Kanbus user
  I want a now feed in the web console
  So that I can review recently-updated issues and their right-now summaries

  Scenario: Now panel falls back to the repository directory name
    Given a Kanbus project with default configuration
    And the console is open
    When I switch to the "Now" view
    Then the now panel board title should be the repository directory name

  Scenario: Now panel shows the configured board name
    Given a Kanbus project with default configuration
    And the Kanbus configuration has name "Chattic.us"
    And the console is open
    When I switch to the "Now" view
    Then the now panel board title should be "Chattic.us"

  Scenario: Now is the first panel mode
    Given the console is open
    Then the panel mode selector labels should be "Now, Board, Wiki, Metrics"
    When I switch to the "Now" view
    Then the current status view should be active
    And the board view should be inactive
    And the type filter selector should be hidden

  Scenario: Board view shows the type filter
    Given the console is open
    When I switch to the "Board" view
    Then the type filter selector should be visible

  Scenario: Now panel defaults to tree view
    Given the console is open
    And no issues exist in the console
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    When I switch to the "Now" view
    Then the status tree view should be enabled
    And the status tree should list issues in order "Initiative Alpha"

  Scenario: Selecting now shows reverse-chronological feed after disabling tree
    Given the console is open
    And no issues exist in the console
    And a status issue "Older task" updated at "2026-01-01T10:00:00.000Z"
    And a status issue "Newer task" updated at "2026-01-02T10:00:00.000Z"
    When I switch to the "Now" view
    And I disable the status tree view
    Then the status feed should list issues in order "Newer task, Older task"

  Scenario: Feed row shows issue title and right-now summary
    Given the console is open
    And no issues exist in the console
    And a status issue "Alpha task" updated at "2026-01-01T10:00:00.000Z"
    And the status issue "Alpha task" has right-now summary "Working on alpha"
    When I switch to the "Now" view
    And I disable the status tree view
    Then the status feed row for "Alpha task" should show title "Alpha task"
    And the status feed row for "Alpha task" should show right-now summary "Working on alpha"

  Scenario: Missing right-now summary shows placeholder
    Given the console is open
    And no issues exist in the console
    And a status issue "Beta task" updated at "2026-01-01T10:00:00.000Z"
    When I switch to the "Now" view
    And I disable the status tree view
    Then the status feed row for "Beta task" should show right-now summary "(no right-now summary)"

  Scenario: Live update refreshes feed row
    Given the console is open
    And no issues exist in the console
    And a status issue "Gamma task" updated at "2026-01-01T10:00:00.000Z"
    And the status issue "Gamma task" has right-now summary "Initial summary"
    And I switch to the "Now" view
    And I disable the status tree view
    When the right-now summary for "Gamma task" is updated to "Updated summary"
    Then the status feed row for "Gamma task" should show right-now summary "Updated summary"

  Scenario: Feed is limited to the most recent issues
    Given the console is open
    And no issues exist in the console
    And 35 status issues exist with sequential update times
    When I switch to the "Now" view
    And I disable the status tree view
    Then the status feed should contain 30 rows

  @console-server
  Scenario: Realtime issue update refreshes current status feed row
    Given the console is open
    And a Kanbus project with default configuration
    And no issues exist in the console
    And a status issue "Live task" updated at "2026-01-01T10:00:00.000Z"
    And the status issue "Live task" has right-now summary "Before update"
    And the console server is running

    And I switch to the "Now" view
    And I disable the status tree view
    When the console receives an issue update for "Live task" with right-now summary "After update"
    Then the status feed row for "Live task" should show right-now summary "After update"

  Scenario: Tree toggle shows hierarchical status feed
    Given the console is open
    And no issues exist in the console
    And the console right now configuration has default_tree_expanded true
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Task Gamma" of type "task" under "Epic Beta" updated at "2026-01-03T10:00:00.000Z"
    When I switch to the "Now" view
    Then the status tree should list issues in order "Initiative Alpha, Epic Beta, Task Gamma"

  Scenario: Tree nodes are collapsible
    Given the console is open
    And no issues exist in the console
    And the console right now configuration has default_tree_expanded true
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Task Gamma" of type "task" under "Epic Beta" updated at "2026-01-03T10:00:00.000Z"
    When I switch to the "Now" view
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
    When I switch to the "Now" view
    Then the status tree node for "Initiative Alpha" should be expanded

  Scenario: Tree node default collapse reflects configuration
    Given the console is open
    And no issues exist in the console
    And the console right now configuration has default_tree_expanded false
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    When I switch to the "Now" view
    Then the status tree node for "Initiative Alpha" should be collapsed

  Scenario: Tree siblings are ordered by updated_at descending
    Given the console is open
    And no issues exist in the console
    And the console right now configuration has default_tree_expanded true
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Task Older" of type "task" under "Epic Beta" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Task Newer" of type "task" under "Epic Beta" updated at "2026-01-04T10:00:00.000Z"
    When I switch to the "Now" view
    Then the status tree should list issues in order "Initiative Alpha, Epic Beta, Task Newer, Task Older"

  Scenario: Tree node shows issue title and right-now summary
    Given the console is open
    And no issues exist in the console
    And a status hierarchy root "Task Gamma" of type "task" updated at "2026-01-01T10:00:00.000Z"
    And the status issue "Task Gamma" has right-now summary "Working on gamma"
    When I switch to the "Now" view
    Then the status tree row for "Task Gamma" should show title "Task Gamma"
    And the status tree row for "Task Gamma" should show right-now summary "Working on gamma"

  Scenario: Missing right-now summary shows placeholder in tree
    Given the console is open
    And no issues exist in the console
    And a status hierarchy root "Task Delta" of type "task" updated at "2026-01-01T10:00:00.000Z"
    When I switch to the "Now" view
    Then the status tree row for "Task Delta" should show right-now summary "(no right-now summary)"

  Scenario: Disabling tree toggle returns to flat feed
    Given the console is open
    And no issues exist in the console
    And a status issue "Older task" updated at "2026-01-01T10:00:00.000Z"
    And a status issue "Newer task" updated at "2026-01-02T10:00:00.000Z"
    When I switch to the "Now" view
    And I disable the status tree view
    Then the status feed should list issues in order "Newer task, Older task"

  Scenario: Tree expands descendants that are outside the status filter
    Given the console is open
    And no issues exist in the console
    And a status hierarchy root "Phase Epic" of type "epic" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Child task" of type "task" under "Phase Epic" updated at "2026-01-03T10:00:00.000Z"
    And the status issue "Child task" has status "open"
    When I switch to the "Now" view
    Then the status tree node for "Phase Epic" should be expandable
    And the status tree node for "Phase Epic" should be collapsed
    And the status tree should list issues in order "Phase Epic"
    When I expand the status tree node for "Phase Epic"
    Then the status tree should list issues in order "Phase Epic, Child task"

  Scenario: Nested descendants stay expandable after a parent is expanded
    Given the console is open
    And no issues exist in the console
    And a status hierarchy root "Initiative Alpha" of type "initiative" updated at "2026-01-01T10:00:00.000Z"
    And a status hierarchy child "Epic Beta" of type "epic" under "Initiative Alpha" updated at "2026-01-02T10:00:00.000Z"
    And a status hierarchy child "Task Gamma" of type "task" under "Epic Beta" updated at "2026-01-03T10:00:00.000Z"
    And the status issue "Epic Beta" has status "open"
    And the status issue "Task Gamma" has status "open"
    When I switch to the "Now" view
    And I expand the status tree node for "Initiative Alpha"
    Then the status tree should list issues in order "Initiative Alpha, Epic Beta"
    And the status tree node for "Epic Beta" should be expandable
    And the status tree node for "Epic Beta" should be collapsed
    When I expand the status tree node for "Epic Beta"
    Then the status tree should list issues in order "Initiative Alpha, Epic Beta, Task Gamma"

  Scenario: Now panel defaults to in-progress issues
    Given the console is open
    And no issues exist in the console
    And a status issue "Active task" updated at "2026-01-02T10:00:00.000Z"
    And a status issue "Ready task" updated at "2026-01-03T10:00:00.000Z"
    And the status issue "Ready task" has status "open"
    When I switch to the "Now" view
    And I disable the status tree view
    Then the status feed should list issues in order "Active task"

  Scenario: Now panel status filter can show all statuses
    Given the console is open
    And no issues exist in the console
    And a status issue "Active task" updated at "2026-01-02T10:00:00.000Z"
    And a status issue "Ready task" updated at "2026-01-03T10:00:00.000Z"
    And the status issue "Ready task" has status "open"
    When I switch to the "Now" view
    And I select the now status filter "all"
    And I disable the status tree view
    Then the status feed should list issues in order "Ready task, Active task"
