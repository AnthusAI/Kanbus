Feature: Dependency flow interoperability
  As a Kanbus user
  I want dependencies to work consistently between Beads and Kanbus modes
  So that I can use either tool interchangeably

  Scenario: Add blocked-by dependency via Beads mode visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-blocker" exists
    And a kanbus issue "bdx-blocked" exists
    When I run "kanbus --beads dep bdx-blocked blocked-by bdx-blocker"
    Then the command should succeed
    When I run "kanbus show bdx-blocked"
    Then stdout should contain "bdx-blocker"

  Scenario: Add blocked-by dependency via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-blocker" exists
    And a kanbus issue "bdx-blocked" exists
    When I run "kanbus dep bdx-blocked blocked-by bdx-blocker"
    Then the command should succeed
    When I run "kanbus --beads show bdx-blocked"
    Then stdout should contain "bdx-blocker"

  Scenario: Add parent-child via Beads mode creates hierarchy in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-parent" exists
    When I run "kanbus --beads create Child issue --parent bdx-parent"
    Then the command should succeed
    And stdout should contain "bdx-parent.1"
    When I run "kanbus list"
    Then stdout should contain "bdx-parent.1"

  Scenario: Add parent-child via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-parent" exists
    When I run "kanbus create Child issue --parent bdx-parent"
    Then the command should succeed
    When I run "kanbus --beads list"
    Then stdout should contain parent reference

  Scenario: Remove dependency via Beads mode reflected in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-blocker" exists
    And a kanbus issue "bdx-blocked" exists with dependency "blocked-by bdx-blocker"
    When I run "kanbus --beads dep bdx-blocked remove blocked-by bdx-blocker"
    Then the command should succeed
    When I run "kanbus show bdx-blocked"
    Then stdout should not contain "bdx-blocker"

  Scenario: Remove dependency via Kanbus reflected in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-blocker" exists
    And a kanbus issue "bdx-blocked" exists with dependency "blocked-by bdx-blocker"
    When I run "kanbus dep bdx-blocked remove blocked-by bdx-blocker"
    Then the command should succeed
    When I run "kanbus --beads show bdx-blocked"
    Then stdout should not contain "bdx-blocker"

  Scenario: Multiple dependencies via both modes preserved
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-one" exists
    And a kanbus issue "bdx-two" exists
    And a kanbus issue "bdx-target" exists
    When I run "kanbus dep bdx-target blocked-by bdx-one"
    And I run "kanbus --beads dep bdx-target blocked-by bdx-two"
    Then the command should succeed
    When I run "kanbus show bdx-target"
    Then stdout should contain "bdx-one"
    And stdout should contain "bdx-two"
    When I run "kanbus --beads show bdx-target"
    Then stdout should contain "bdx-one"
    And stdout should contain "bdx-two"

  Scenario: Parent-child relationships prevent circular dependencies
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-parent" exists
    And a kanbus issue "bdx-parent.1" exists with parent "bdx-parent"
    When I run "kanbus dep bdx-parent blocked-by bdx-parent.1"
    Then the command should fail with exit code 1
    And stderr should contain "circular"

  Scenario: Ready command respects blocked-by across modes
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-blocker" exists with status "open"
    And a kanbus issue "bdx-blocked" exists with dependency "blocked-by bdx-blocker"
    When I run "kanbus ready"
    Then stdout should not contain "bdx-blocked"
    When I run "kanbus --beads ready"
    Then stdout should not contain "bdx-blocked"
