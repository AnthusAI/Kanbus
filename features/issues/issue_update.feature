Feature: Issue update

  Scenario: Update issue title and description
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Old Title"
    When I run "kanbus update kanbus-aaa --title \"New Title\" --description \"Updated description\""
    Then the command should succeed
    And stdout should contain "Updated kanbus-aaa"
    And issue "kanbus-aaa" should have title "New Title"
    And issue "kanbus-aaa" should have description "Updated description"
    And issue "kanbus-aaa" should have an updated_at timestamp

  Scenario: Update issue status with a valid transition
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with status "open"
    When I run "kanbus update kanbus-aaa --status in_progress"
    Then the command should succeed
    And stdout should contain "Updated kanbus-aaa"
    And issue "kanbus-aaa" should have status "in_progress"

  Scenario: Reject invalid status transition
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with status "open"
    When I run "kanbus update kanbus-aaa --status blocked"
    Then the command should fail with exit code 1
    And stderr should contain "invalid transition"
    And issue "kanbus-aaa" should have status "open"

  Scenario: Reject unknown status
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with status "open"
    When I run "kanbus update kanbus-aaa --status does_not_exist"
    Then the command should fail with exit code 1
    And stderr should contain "unknown status"
    And issue "kanbus-aaa" should have status "open"

  Scenario: Update bypasses validation with --no-validate
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with status "open"
    When I run "kanbus update kanbus-aaa --status does_not_exist --no-validate"
    Then the command should succeed
    And issue "kanbus-aaa" should have status "does_not_exist"

  Scenario: Update missing issue fails
    Given a Kanbus project with default configuration
    When I run "kanbus update kanbus-missing --title \"New Title\""
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Update fails when no changes are requested
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Old Title"
    When I run "kanbus update kanbus-aaa"
    Then the command should fail with exit code 1
    And stderr should contain "no updates requested"

  Scenario: Update fails when title already exists
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Old Title"
    And an issue "kanbus-bbb" exists with title "Duplicate Title"
    When I run "kanbus update kanbus-aaa --title \"duplicate title\""
    Then the command should fail with exit code 1
    And stderr should contain "duplicate title"
    And stderr should contain "kanbus-bbb"

  Scenario: Update fails without a project
    Given an empty git repository
    When I run "kanbus update kanbus-aaa --title \"New Title\""
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"
