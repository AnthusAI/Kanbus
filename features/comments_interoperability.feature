Feature: Comments flow interoperability
  As a Kanbus user
  I want comments to work consistently between Beads and Kanbus modes
  So that I can use either tool interchangeably

  Scenario: Add comment via Beads mode visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus --beads comment bdx-test First comment"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "First comment"

  Scenario: Add comment via Kanbus visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus comment bdx-test First comment"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "First comment"

  Scenario: Multiple comments via Beads mode all visible in Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus --beads comment bdx-test First comment"
    And I run "kanbus --beads comment bdx-test Second comment"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "First comment"
    And stdout should contain "Second comment"

  Scenario: Multiple comments via Kanbus all visible in Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus comment bdx-test First comment"
    And I run "kanbus comment bdx-test Second comment"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "First comment"
    And stdout should contain "Second comment"

  Scenario: Comments added via both modes all visible
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus comment bdx-test Kanbus comment"
    And I run "kanbus --beads comment bdx-test Beads comment"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "Kanbus comment"
    And stdout should contain "Beads comment"
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "Kanbus comment"
    And stdout should contain "Beads comment"

  Scenario: Comment on Beads-only issue via Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a beads issue "bdx-old" exists
    When I run "kanbus comment bdx-old Comment from Kanbus"
    Then the command should succeed
    When I run "kanbus --beads show bdx-old"
    Then stdout should contain "Comment from Kanbus"

  Scenario: Comment with multiline text via Beads mode
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus --beads comment bdx-test --body-file -" with stdin "First line\nSecond line"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then stdout should contain "First line"
    And stdout should contain "Second line"

  Scenario: Comment with multiline text via Kanbus
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus comment bdx-test --body-file -" with stdin "First line\nSecond line"
    Then the command should succeed
    When I run "kanbus --beads show bdx-test"
    Then stdout should contain "First line"
    And stdout should contain "Second line"

  Scenario: Comments preserve order across modes
    Given a Kanbus project with beads compatibility enabled
    And a kanbus issue "bdx-test" exists
    When I run "kanbus comment bdx-test Comment 1"
    And I run "kanbus --beads comment bdx-test Comment 2"
    And I run "kanbus comment bdx-test Comment 3"
    Then the command should succeed
    When I run "kanbus show bdx-test"
    Then the comments should appear in order: "Comment 1", "Comment 2", "Comment 3"
