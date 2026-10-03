Feature: Dynamic short IDs
  Issue identifiers are displayed with the fewest characters needed to keep
  every visible ID unique, and ambiguous candidates fail loudly instead of
  guessing.

  Background:
    Given a Kanbus project with default configuration

  Scenario: Collision-free issues display at the default width
    Given an issue "kanbus-0123456789ab" exists
    When I run "kanbus list"
    Then stdout should contain " 0123 "
    And stdout should not contain "012345"

  Scenario: Colliding short IDs are widened until unique
    Given a project issue "kanbus-aaaabbbb" exists with title "Alpha"
    And a project issue "kanbus-aaaacccc" exists with title "Bravo"
    And a project issue "kanbus-9f8e7d6c" exists with title "Zulu"
    When I run "kanbus list"
    Then the list should show short ID "aaaab" for issue "kanbus-aaaabbbb"
    And the list should show short ID "aaaac" for issue "kanbus-aaaacccc"
    And the list should show short ID "9f8e" for issue "kanbus-9f8e7d6c"

  Scenario: Every displayed short ID in the list is unique
    Given project issues exist from the short ID uniqueness fixture
    When I run "kanbus list"
    Then no two displayed list IDs should collide
    And no displayed short ID should be ambiguous in the visible set

  Scenario: Configured short_id_length overrides the default width
    Given the Kanbus configuration sets short_id_length to 6
    And an issue "kanbus-0123456789ab" exists
    When I run "kanbus list"
    Then stdout should contain "012345"
    And stdout should not contain "0123456789ab"

  Scenario: Beads compatibility defaults to 6-character short IDs
    Given a Kanbus project with beads compatibility enabled
    And a beads issue with id "kanbus-0123456789ab" exists
    When I run "kanbus list"
    Then stdout should contain "kanbus-012345"
    And stdout should not contain "kanbus-0123456789ab"

  Scenario: Beads compatibility respects an explicit short_id_length
    Given a Kanbus project with beads compatibility enabled
    And the Kanbus configuration sets short_id_length to 4
    And a beads issue with id "kanbus-0123456789ab" exists
    When I run "kanbus list"
    Then stdout should contain "kanbus-0123"
    And stdout should not contain "kanbus-012345"

  Scenario: Identifier resolution ignores hyphens
    Given a project issue "kanbus-aaaabbbb" exists with title "Alpha"
    When I run "kanbus show kanbus-aaaabbbb"
    Then the command should succeed
    When I run "kanbus show kanbusaaaabbbb"
    Then the command should succeed
    And stdout should contain "Alpha"

  Scenario: Ambiguous short IDs fail with exit code 3
    Given a project issue "kanbus-aaaabbbb" exists with title "Alpha"
    And a project issue "kanbus-aaaacccc" exists with title "Bravo"
    When I run "kanbus show kanbus-aaaa"
    Then the command exit code should be 3
    And stderr should contain "ambiguous identifier"
    And stderr should contain "Alpha"
    And stderr should contain "Bravo"

  Scenario: Ambiguous short IDs return structured matches with --json
    Given a project issue "kanbus-aaaabbbb" exists with title "Alpha"
    And a project issue "kanbus-aaaacccc" exists with title "Bravo"
    When I run "kanbus show kanbus-aaaa --json"
    Then the command exit code should be 3
    And the ambiguity JSON should list full IDs "kanbus-aaaabbbb, kanbus-aaaacccc"
