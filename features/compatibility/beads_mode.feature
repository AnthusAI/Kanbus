Feature: Beads compatibility mode
  As a Kanbus user
  I want to read Beads issues directly
  So that I can evaluate Kanbus without migrating

  Scenario: List Beads issues
    Given a git repository with a .beads issues database
    And a project directory exists
    When I run "kanbus --beads list"
    Then the command should succeed
    And stdout should list issue "bdx-epic"
    And stdout should not list issue "bdx-task"

  Scenario: Ready excludes closed Beads issues
    Given a git repository with a .beads issues database
    And a project directory exists
    When I run "kanbus --beads ready"
    Then the command should succeed
    And stdout should contain "bdx-epic"
    And stdout should not contain "bdx-task"

  Scenario: Show reads Beads issue details
    Given a git repository with a .beads issues database
    And a project directory exists
    When I run "kanbus --beads show bdx-epic"
    Then the command should succeed
    And stdout should contain "Sample epic"

  Scenario: Beads mode maps feature issues to story
    Given a git repository with a Beads feature issue
    When I run "kanbus --beads show bdx-feature"
    Then the command should succeed
    And stdout should contain "story"

  Scenario: Create Beads issue in compatibility mode
    Given a git repository with a .beads issues database
    And a project directory exists
    When I run "kanbus --beads create New beads child --parent bdx-epic"
    Then the command should succeed
    And stdout should contain "bdx-epic.1"
    And beads issues.jsonl should contain "bdx-epic.1"

  Scenario: Beads mode fails when .beads is missing
    Given a git repository without a .beads directory
    And a project directory exists
    When I run "kanbus --beads list"
    Then the command should fail with exit code 1
    And stderr should contain "no .beads directory"

  Scenario: Beads mode fails when issues.jsonl is missing
    Given a git repository with an empty .beads directory
    And a project directory exists
    When I run "kanbus --beads list"
    Then the command should fail with exit code 1
    And stderr should contain "no issues.jsonl"

  Scenario: Beads mode rejects local filtering for list
    Given a git repository with a .beads issues database
    And a project directory exists
    When I run "kanbus --beads list --no-local"
    Then the command should fail with exit code 1
    And stderr should contain "beads mode does not support local filtering"

  Scenario: Beads mode rejects local filtering for ready
    Given a git repository with a .beads issues database
    And a project directory exists
    When I run "kanbus --beads ready --no-local"
    Then the command should fail with exit code 1
    And stderr should contain "beads mode does not support local filtering"

  Scenario: Beads mode ready fails when .beads is missing
    Given a git repository without a .beads directory
    And a project directory exists
    When I run "kanbus --beads ready"
    Then the command should fail with exit code 1
    And stderr should contain "no .beads directory"

  Scenario: Beads mode show fails when issue is missing
    Given a git repository with a .beads issues database
    And a project directory exists
    When I run "kanbus --beads show bdx-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Beads compatibility config enables Beads mode
    Given a Kanbus project with beads compatibility enabled
    When I run "kanbus list"
    Then the command should succeed
    And stdout should contain "bdx-epic"
