Feature: ID formats differ between Beads mode and Kanbus mode
  As a Kanbus developer
  I want to see distinct ID formats in Beads compatibility and native Kanbus modes
  So that UUID-based IDs are used after migration while Beads retains its numbering

  Background:
    Given a Beads fixture repository

  Scenario: Beads mode creates an epic with Beads-style slug
    When I run "kanbus --beads create Beads epic --type epic"
    Then the command should succeed
    And stdout should match pattern "bdx-[a-z0-9]{3}"
    And beads issues.jsonl should contain an id matching "bdx-[a-z0-9]{3}"

  Scenario: Beads mode creates a task under an epic with numeric child id
    When I run "kanbus --beads create Beads child --parent bdx-epic"
    Then the command should succeed
    And stdout should match pattern "bdx-epic.[0-9]+"
    And beads issues.jsonl should contain an id matching "bdx-epic.[0-9]+"

  Scenario: Native Kanbus mode creates an epic with UUID id
    Given a migrated Kanbus repository from the Beads fixture
    And I record existing Kanbus issue ids
    When I run "kanbus create Native epic --type epic"
    Then the command should succeed
    And the last Kanbus issue id should match "kanbus-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

  Scenario: Native Kanbus mode creates a task with UUID id under epic
    Given a migrated Kanbus repository from the Beads fixture
    And I record existing Kanbus issue ids
    And I run "kanbus create Native epic --type epic"
    And I record the new Kanbus issue id
    When I create a native task under the recorded Kanbus epic
    Then the command should succeed
    And the last Kanbus issue id should match "kanbus-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

  Scenario: Delete in Kanbus removes issue from both lists after native creation
    Given a migrated Kanbus repository from the Beads fixture
    And I record existing Kanbus issue ids
    When I run "kanbus create Native deletable --type epic"
    Then the command should succeed
    And the last Kanbus issue id should be recorded
    When I run "kanbus list"
    Then the command should succeed
    And the recorded Kanbus issue id should appear in the Kanbus list output
    When I delete the recorded Kanbus issue
    Then the command should succeed
    When I run "kanbus list"
    Then the command should succeed
    And the recorded Kanbus issue id should not appear in the Kanbus list output
