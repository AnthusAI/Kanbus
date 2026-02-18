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

  Scenario: Ensure comment ids are assigned for legacy comments
    Given a Kanbus project with default configuration
    And an issue "kanbus-legacy" exists with a comment missing an id
    When I ensure comment ids for "kanbus-legacy"
    Then issue "kanbus-legacy" should have comment ids assigned

  Scenario: Update comment text by id prefix
    Given a Kanbus project with default configuration
    And an issue "kanbus-update" exists with comment id "abc123" and text "Original"
    When I update comment "abc" on "kanbus-update" to "Updated"
    Then issue "kanbus-update" should have comment text "Updated"

  Scenario: Delete comment by id prefix
    Given a Kanbus project with default configuration
    And an issue "kanbus-delete" exists with comment id "deadbeef" and text "Remove me"
    When I delete comment "dead" on "kanbus-delete"
    Then issue "kanbus-delete" should have 0 comments

  Scenario: Update comment with ambiguous prefix fails
    Given a Kanbus project with default configuration
    And an issue "kanbus-ambig" exists with comment ids "abc111" and "abc222"
    When I attempt to update comment "abc" on "kanbus-ambig" to "Nope"
    Then the last comment operation should fail with "ambiguous"

  Scenario: Update comment with empty id prefix fails
    Given a Kanbus project with default configuration
    And an issue "kanbus-empty" exists with comment id "abc111" and text "Hello"
    When I attempt to update comment "<empty>" on "kanbus-empty" to "Nope"
    Then the last comment operation should fail with "comment id is required"

  Scenario: Update comment with unknown prefix fails
    Given a Kanbus project with default configuration
    And an issue "kanbus-missing-prefix" exists with comment id "abc111" and text "Hello"
    When I attempt to update comment "zzz" on "kanbus-missing-prefix" to "Nope"
    Then the last comment operation should fail with "comment not found"

  Scenario: Ensure comment ids on missing issue fails
    Given a Kanbus project with default configuration
    When I attempt to ensure comment ids for "kanbus-missing"
    Then the last comment operation should fail with "not found"

  Scenario: Update comment on missing issue fails
    Given a Kanbus project with default configuration
    When I attempt to update comment "abc" on "kanbus-missing" to "Nope"
    Then the last comment operation should fail with "not found"

  Scenario: Delete comment on missing issue fails
    Given a Kanbus project with default configuration
    When I attempt to delete comment "abc" on "kanbus-missing"
    Then the last comment operation should fail with "not found"
