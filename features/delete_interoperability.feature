Feature: Delete flow interoperability
  As a Kanbus user
  I want deletes to work consistently between Beads and Kanbus modes
  So that I can use either tool interchangeably

  Scenario: Delete via Beads mode removes from Kanbus list
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus --beads delete bdx-test"
    Then the command should succeed
    And beads issues.jsonl should not contain "bdx-test"
    When I run "kanbus list"
    Then stdout should not contain "bdx-test"

  Scenario: Delete via Kanbus removes from Beads mode list
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus delete bdx-test"
    Then the command should succeed
    When I run "kanbus --beads list"
    Then stdout should not contain "bdx-test"

  Scenario: Beads mode delete fails for Kanbus-only issue
    Given a Kanbus project with beads compatibility enabled
    And a kanbus-only issue "tsk-only" exists
    When I run "kanbus --beads delete tsk-only"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Kanbus delete removes Beads issue
    Given a Kanbus project with beads compatibility enabled
    And a beads issue "bdx-old" exists
    When I run "kanbus delete bdx-old"
    Then the command should succeed
    And beads issues.jsonl should not contain "bdx-old"

  Scenario: Delete via Beads mode preserves child issues
    Given a Kanbus project with beads compatibility enabled
    And a beads issue "bdx-parent" exists
    And a beads issue "bdx-parent.1" exists with parent "bdx-parent"
    When I run "kanbus --beads delete bdx-parent"
    Then the command should succeed
    And beads issues.jsonl should not contain "bdx-parent"
    And beads issues.jsonl should contain "bdx-parent.1"

  Scenario: Delete via Kanbus preserves child issues
    Given a Kanbus project with beads compatibility enabled
    And a beads issue "bdx-parent" exists
    And a beads issue "bdx-parent.1" exists with parent "bdx-parent"
    When I run "kanbus delete bdx-parent"
    Then the command should succeed
    When I run "kanbus --beads list"
    Then stdout should not contain "bdx-parent"
    And stdout should contain "bdx-parent.1"
