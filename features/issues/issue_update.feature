Feature: Issue update

  Scenario: Update issue title and description
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists with title "Old Title"
    When I run "tsk update tsk-aaa --title \"New Title\" --description \"Updated description\""
    Then the command should succeed
    And issue "tsk-aaa" should have title "New Title"
    And issue "tsk-aaa" should have description "Updated description"
    And issue "tsk-aaa" should have an updated_at timestamp

  Scenario: Update issue status with a valid transition
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists with status "open"
    When I run "tsk update tsk-aaa --status in_progress"
    Then the command should succeed
    And issue "tsk-aaa" should have status "in_progress"

  Scenario: Reject invalid status transition
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists with status "open"
    When I run "tsk update tsk-aaa --status blocked"
    Then the command should fail with exit code 1
    And stderr should contain "invalid transition"
    And issue "tsk-aaa" should have status "open"

  Scenario: Update missing issue fails
    Given a Taskulus project with default configuration
    When I run "tsk update tsk-missing --title \"New Title\""
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Update fails without a project
    Given an empty git repository
    When I run "tsk update tsk-aaa --title \"New Title\""
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"
