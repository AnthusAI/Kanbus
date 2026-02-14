Feature: Beads compatibility write errors
  As a Kanbus user
  I want Beads write operations to fail with clear errors
  So that compatibility mode is predictable

  Scenario: Beads mode create rejects local issues
    Given a git repository with a .beads issues database
    When I run "kanbus --beads create Local beads issue --local"
    Then the command should fail with exit code 1
    And stderr should contain "beads mode does not support local issues"

  Scenario: Beads mode create fails when .beads is missing
    Given a git repository without a .beads directory
    When I run "kanbus --beads create Missing beads issue"
    Then the command should fail with exit code 1
    And stderr should contain "no .beads directory"

  Scenario: Beads mode create fails when issues.jsonl is missing
    Given a git repository with an empty .beads directory
    When I run "kanbus --beads create Missing issues file"
    Then the command should fail with exit code 1
    And stderr should contain "no issues.jsonl"

  Scenario: Beads mode create fails when issues.jsonl is empty
    Given a git repository with an empty issues.jsonl file
    When I run "kanbus --beads create Empty beads file"
    Then the command should fail with exit code 1
    And stderr should contain "no beads issues available"

  Scenario: Beads mode create fails when parent is missing
    Given a git repository with a .beads issues database
    When I run "kanbus --beads create Orphan beads issue --parent bdx-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Beads mode create writes assignee
    Given a git repository with a .beads issues database
    When I run "kanbus --beads create Assigned beads issue --assignee dev@example.com"
    Then the command should succeed
    And beads issues.jsonl should include assignee "dev@example.com"

  Scenario: Beads mode create writes description
    Given a git repository with a .beads issues database
    When I run "kanbus --beads create Described beads issue --description Details"
    Then the command should succeed
    And beads issues.jsonl should include description "Details"

  Scenario: Beads mode create skips blank lines
    Given a git repository with a .beads issues database containing blank lines
    When I run "kanbus --beads create Beads with blanks"
    Then the command should succeed

  Scenario: Beads mode create rejects invalid beads ids
    Given a git repository with a .beads issues database containing an invalid id
    When I run "kanbus --beads create Invalid prefix"
    Then the command should fail with exit code 1
    And stderr should contain "invalid beads id"

  Scenario: Beads mode create fails after repeated slug collisions
    Given a git repository with a .beads issues database
    And the beads slug generator always returns "abc"
    And a beads issue with id "bdx-abc" exists
    When I run "kanbus --beads create Colliding beads issue"
    Then the command should fail with exit code 1
    And stderr should contain "unable to generate unique id after 10 attempts"

  Scenario: Beads mode creates next child suffix
    Given a git repository with a .beads issues database
    And a beads issue with id "bdx-epic.9" exists
    When I run "kanbus --beads create Next child --parent bdx-epic"
    Then the command should succeed
    And stdout should contain "bdx-epic.10"

  Scenario: Beads mode update fails when issue is missing
    Given a git repository with a .beads issues database
    When I run "kanbus --beads update bdx-missing --status closed"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Beads mode update fails when .beads is missing
    Given a git repository without a .beads directory
    When I run "kanbus --beads update bdx-epic --status closed"
    Then the command should fail with exit code 1
    And stderr should contain "no .beads directory"

  Scenario: Beads mode update fails when issues.jsonl is missing
    Given a git repository with an empty .beads directory
    When I run "kanbus --beads update bdx-epic --status closed"
    Then the command should fail with exit code 1
    And stderr should contain "no issues.jsonl"

  Scenario: Beads mode update writes status
    Given a git repository with a .beads issues database
    When I run "kanbus --beads update bdx-epic --status closed"
    Then the command should succeed
    And beads issues.jsonl should include status "closed" for "bdx-epic"

  Scenario: Beads mode delete fails when .beads is missing
    Given a git repository without a .beads directory
    When I run "kanbus --beads delete bdx-missing"
    Then the command should fail with exit code 1
    And stderr should contain "no .beads directory"

  Scenario: Beads mode delete fails when issues.jsonl is missing
    Given a git repository with an empty .beads directory
    When I run "kanbus --beads delete bdx-missing"
    Then the command should fail with exit code 1
    And stderr should contain "no issues.jsonl"

  Scenario: Beads mode delete fails when issue is missing
    Given a git repository with a .beads issues database
    When I run "kanbus --beads delete bdx-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Beads mode delete removes issue
    Given a git repository with a .beads issues database
    When I run "kanbus --beads delete bdx-task"
    Then the command should succeed
    And beads issues.jsonl should not contain "bdx-task"
