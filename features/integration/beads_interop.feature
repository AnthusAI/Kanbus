Feature: Beads interoperability end-to-end
  As a Kanbus developer
  I want Kanbus and Beads data to interoperate
  So that I can read and write Beads issues via Kanbus in compatibility mode

  Background:
    Given a Beads fixture repository

  Scenario: Kanbus lists existing Beads issues
    When I run "kanbus --beads list"
    Then the command should succeed
    And stdout should contain "E epic"
    And stdout should contain "T task"

  Scenario: Create in Kanbus and see in Beads
    When I run "kanbus --beads create Interop child via Kanbus --parent bdx-epic"
    Then the command should succeed
    And the last created beads issue should exist in beads issues.jsonl

  Scenario: Update in Kanbus and see update in Beads
    When I run "kanbus --beads create Interop updatable --parent bdx-epic"
    And I update the last created beads issue to status "closed"
    Then beads issues.jsonl should show the last created beads issue with status "closed"
    And stdout should contain "Updated"

  Scenario: Delete in Kanbus removes issue from both lists
    When I run "kanbus --beads create Interop deletable --parent bdx-epic"
    Then the command should succeed
    And the last created beads issue should exist in beads issues.jsonl
    When I run "kanbus --beads list"
    Then the command should succeed
    And the last created beads issue should appear in the Kanbus beads list output
    And beads issues.jsonl should contain the last created beads issue
    When I delete the last created beads issue
    Then the command should succeed
    And beads issues.jsonl should not contain the last created beads issue
    When I run "kanbus --beads list"
    Then the command should succeed
    And the last created beads issue should not appear in the Kanbus beads list output
