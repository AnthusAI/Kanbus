Feature: ID formats differ between Beads mode and Taskulus mode
  As a Taskulus developer
  I want to see distinct ID formats in Beads compatibility and native Taskulus modes
  So that UUID-based IDs are used after migration while Beads retains its numbering

  Background:
    Given a Beads fixture repository

  Scenario: Beads mode creates an epic with Beads-style slug
    When I run "tsk --beads create Beads epic --type epic"
    Then the command should succeed
    And stdout should match pattern "bdx-[a-z0-9]{3}"
    And beads issues.jsonl should contain an id matching "bdx-[a-z0-9]{3}"

  Scenario: Beads mode creates a task under an epic with numeric child id
    When I run "tsk --beads create Beads child --parent bdx-epic"
    Then the command should succeed
    And stdout should match pattern "bdx-epic.[0-9]+"
    And beads issues.jsonl should contain an id matching "bdx-epic.[0-9]+"

  Scenario: Native Taskulus mode creates an epic with UUID id
    Given a migrated Taskulus repository from the Beads fixture
    And I record existing Taskulus issue ids
    When I run "tsk create Native epic --type epic"
    Then the command should succeed
    And the last Taskulus issue id should match "tsk-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

  Scenario: Native Taskulus mode creates a task with UUID id under epic
    Given a migrated Taskulus repository from the Beads fixture
    And I record existing Taskulus issue ids
    And I run "tsk create Native epic --type epic"
    And I record the new Taskulus issue id
    When I create a native task under the recorded Taskulus epic
    Then the command should succeed
    And the last Taskulus issue id should match "tsk-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

  Scenario: Delete in Taskulus removes issue from both lists after native creation
    Given a migrated Taskulus repository from the Beads fixture
    And I record existing Taskulus issue ids
    When I run "tsk create Native deletable --type epic"
    Then the command should succeed
    And the last Taskulus issue id should be recorded
    When I run "tsk list"
    Then the command should succeed
    And the recorded Taskulus issue id should appear in the Taskulus list output
    When I delete the recorded Taskulus issue
    Then the command should succeed
    When I run "tsk list"
    Then the command should succeed
    And the recorded Taskulus issue id should not appear in the Taskulus list output
