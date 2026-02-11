@wip
Feature: Issue comments
  As a Taskulus user
  I want to add comments to issues
  So that important context is preserved alongside the work

  @wip
  Scenario: Add a comment to an issue
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists
    And the current user is "dev@example.com"
    When I run "tsk comment tsk-aaa \"First comment\""
    Then the command should succeed
    And issue "tsk-aaa" should have 1 comment
    And the latest comment should have author "dev@example.com"
    And the latest comment should have text "First comment"
    And the latest comment should have a created_at timestamp

  @wip
  Scenario: Comment on a missing issue fails
    Given a Taskulus project with default configuration
    When I run "tsk comment tsk-missing \"Missing issue note\""
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  @wip
  Scenario: Comments remain in chronological order
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists
    And the current user is "dev@example.com"
    When I run "tsk comment tsk-aaa \"First comment\""
    And I run "tsk comment tsk-aaa \"Second comment\""
    Then issue "tsk-aaa" should have comments in order "First comment", "Second comment"
