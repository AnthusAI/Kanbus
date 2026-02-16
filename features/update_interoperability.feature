Feature: Update flow interoperability
  As a Kanbus user
  I want updates to work consistently between Beads and Kanbus modes
  So that I can use either tool interchangeably

  Scenario: Update title via Beads mode visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with title "Original title"
    When I run "kanbus --beads update bdx-test --title Updated title"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "Updated title"

  Scenario: Update title via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with title "Original title"
    When I run "kanbus update bdx-test --title Updated title"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "Updated title"

  Scenario: Update description via Beads mode visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus --beads update bdx-test --description New description"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "New description"

  Scenario: Update description via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus update bdx-test --description New description"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "New description"

  Scenario: Update status via Beads mode visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with status "open"
    When I run "kanbus --beads update bdx-test --status closed"
    Then the command should succeed
    And beads issues.jsonl should include status "closed" for "bdx-test"
    When I run "kanbus list --status closed"
    Then stdout should contain "bdx-test"

  Scenario: Update status via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with status "open"
    When I run "kanbus update bdx-test --status closed"
    Then the command should succeed
    When I run "kanbus --beads list"
    Then stdout should not contain "bdx-test"

  Scenario: Update priority via Beads mode visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with priority 2
    When I run "kanbus --beads update bdx-test --priority 0"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "P0"

  Scenario: Update priority via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with priority 2
    When I run "kanbus update bdx-test --priority 0"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "0"

  Scenario: Update assignee via Beads mode visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus --beads update bdx-test --assignee dev@example.com"
    Then the command should succeed
    And beads issues.jsonl should include assignee "dev@example.com"
    When I run "kanbus show bdx-test"
    Then stdout should contain "dev@example.com"

  Scenario: Update assignee via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus update bdx-test --assignee dev@example.com"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "dev@example.com"

  Scenario: Multiple updates via Beads mode preserved in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus --beads update bdx-test --title New title --status in_progress --priority 1"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "New title"
    And stdout should contain "in_progress"
    And stdout should contain "P1"

  Scenario: Multiple updates via Kanbus preserved in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus update bdx-test --title New title --status in_progress --priority 1"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "New title"
    And stdout should contain "in_progress"
    And stdout should contain "1"
