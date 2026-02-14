Feature: Migrate from Beads
  As a Kanbus adopter
  I want to migrate Beads issues into Kanbus
  So that existing project history is preserved

  Scenario: Migrate a repository with Beads issues
    Given a git repository with a .beads issues database
    When I run "kanbus migrate"
    Then the command should succeed
    And a Kanbus project should be initialized
    And all Beads issues should be converted to Kanbus issues

  Scenario: Migration fails when .beads is missing
    Given a git repository without a .beads directory
    When I run "kanbus migrate"
    Then the command should fail with exit code 1
    And stderr should contain "no .beads directory"

  Scenario: Migration fails when issues.jsonl is missing
    Given a git repository with an empty .beads directory
    When I run "kanbus migrate"
    Then the command should fail with exit code 1
    And stderr should contain "no issues.jsonl"

  Scenario: Migration fails when not a git repository
    Given a directory that is not a git repository
    When I run "kanbus migrate"
    Then the command should fail with exit code 1
    And stderr should contain "not a git repository"

  Scenario: Migration is idempotent
    Given a git repository with a .beads issues database
    And a Kanbus project already exists
    When I run "kanbus migrate"
    Then the command should fail with exit code 1
    And stderr should contain "already initialized"

  Scenario: Migration ignores blank lines
    Given a git repository with a .beads issues database containing blank lines
    When I run "kanbus migrate"
    Then the command should succeed
    And all Beads issues should be converted to Kanbus issues

  Scenario: Migration preserves metadata and dependencies
    Given a git repository with Beads metadata and dependencies
    When I run "kanbus migrate"
    Then the command should succeed
    And migrated issues should include metadata and dependencies

  Scenario: Migration preserves mapped issue types
    Given a git repository with a Beads feature issue
    When I run "kanbus migrate"
    Then the command should succeed
    And migrated issue "bdx-feature" should have type "story"
    And migrated issue "bdx-feature" should preserve beads issue type "feature"

  Scenario: Migration preserves same-type parent-child relationships
    Given a git repository with Beads epic parent and child
    When I run "kanbus migrate"
    Then the command should succeed
    And migrated issue "bdx-child" should have parent "bdx-parent"

  Scenario: Migration accepts fractional second timestamps
    Given a git repository with Beads issues containing fractional timestamps
    When I run "kanbus migrate"
    Then the command should succeed
    And all Beads issues should be converted to Kanbus issues

  Scenario: Migration rejects malformed records
    When I validate migration error cases
    Then migration errors should include "missing id"
    And migration errors should include "title is required"
    And migration errors should include "issue_type is required"
    And migration errors should include "status is required"
    And migration errors should include "priority is required"
    And migration errors should include "invalid priority"
    And migration errors should include "unknown issue type"
    And migration errors should include "invalid status"
    And migration errors should include "invalid dependency"
    And migration errors should include "missing dependency"
    And migration errors should include "parent issue_type is required"
    And migration errors should include "invalid comment"
    And migration errors should include "comment.created_at is required"
    And migration errors should include "comment.created_at must be a string"
    And migration errors should include "invalid comment.created_at"
    And migration errors should include "created_at is required"
    And migration errors should include "created_at must be a string"
    And migration errors should include "invalid created_at"
