Feature: Issue comments
  As a Kanbus user
  I want to add comments to issues
  So that important context is preserved alongside the work

  Scenario: Add a comment to an issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And the current user is "dev@example.com"
    When I run "kanbus comment kanbus-aaa \"First comment\""
    Then the command should succeed
    And issue "kanbus-aaa" should have 1 comment
    And the latest comment should have author "dev@example.com"
    And the latest comment should have text "First comment"
    And the latest comment should have a created_at timestamp

  Scenario: Comment on a missing issue fails
    Given a Kanbus project with default configuration
    When I run "kanbus comment kanbus-missing \"Missing issue note\""
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Comments remain in chronological order
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And the current user is "dev@example.com"
    When I run "kanbus comment kanbus-aaa \"First comment\""
    And I run "kanbus comment kanbus-aaa \"Second comment\""
    Then issue "kanbus-aaa" should have comments in order "First comment", "Second comment"
