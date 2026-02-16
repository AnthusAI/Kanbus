Feature: Label flow interoperability
  As a Kanbus user
  I want labels to work consistently between Beads and Kanbus modes
  So that I can use either tool interchangeably

  Scenario: Add label via Beads mode visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus --beads update bdx-test --add-label bug"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "bug"

  Scenario: Add label via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus update bdx-test --add-label bug"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "bug"

  Scenario: Add multiple labels via Beads mode visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus --beads update bdx-test --add-label bug --add-label urgent"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "bug"
    And stdout should contain "urgent"

  Scenario: Add multiple labels via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus update bdx-test --add-label bug --add-label urgent"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "bug"
    And stdout should contain "urgent"

  Scenario: Remove label via Beads mode reflected in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with labels "bug,urgent"
    When I run "kanbus --beads update bdx-test --remove-label bug"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should not contain "bug"
    And stdout should contain "urgent"

  Scenario: Remove label via Kanbus reflected in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with labels "bug,urgent"
    When I run "kanbus update bdx-test --remove-label bug"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should not contain "bug"
    And stdout should contain "urgent"

  Scenario: Set labels via Beads mode replaces all labels in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with labels "old-label"
    When I run "kanbus --beads update bdx-test --set-labels new,labels"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should not contain "old-label"
    And stdout should contain "new"
    And stdout should contain "labels"

  Scenario: Set labels via Kanbus replaces all labels in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists with labels "old-label"
    When I run "kanbus update bdx-test --set-labels new,labels"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should not contain "old-label"
    And stdout should contain "new"
    And stdout should contain "labels"

  Scenario: Labels added via both modes are combined
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus update bdx-test --add-label from-kanbus"
    And I run "kanbus --beads update bdx-test --add-label from-beads"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "from-kanbus"
    And stdout should contain "from-beads"

  Scenario: Filter by label works across modes
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-one" exists with labels "urgent"
    And a kanbus issue "bdx-two" exists with labels "normal"
    When I run "kanbus list --label urgent"
    Then stdout should contain "bdx-one"
    And stdout should not contain "bdx-two"
    When I run "kanbus --beads list --label urgent"
    Then stdout should contain "bdx-one"
    And stdout should not contain "bdx-two"
