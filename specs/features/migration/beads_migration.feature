Feature: Migrate from Beads
  As a Taskulus adopter
  I want to migrate Beads issues into Taskulus
  So that existing project history is preserved

  Scenario: Migrate a repository with Beads issues
    Given a git repository with a .beads issues database
    When I run "tsk migrate"
    Then the command should succeed
    And a Taskulus project should be initialized
    And all Beads issues should be converted to Taskulus issues

  Scenario: Migration fails when .beads is missing
    Given a git repository without a .beads directory
    When I run "tsk migrate"
    Then the command should fail with exit code 1
    And stderr should contain "no .beads directory"

  Scenario: Migration is idempotent
    Given a git repository with a .beads issues database
    And a Taskulus project already exists
    When I run "tsk migrate"
    Then the command should fail with exit code 1
    And stderr should contain "already initialized"
