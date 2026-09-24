Feature: Project rekey
  As a Kanbus maintainer
  I want to rename a project key and all issue IDs
  So that projects can be renamed safely without manual JSON editing

  Scenario: Rekey renames project key and issue IDs with suffix preservation
    Given a Kanbus project with key "old"
    And a "task" issue "old-abc123de-1234-5678-abcd-123456789012" exists
    And a "task" issue "old-def456gh-5678-1234-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-abc123de-1234-5678-abcd-123456789012" should exist
    And issue "new-def456gh-5678-1234-abcd-123456789012" should exist
    And issue "old-abc123de-1234-5678-abcd-123456789012" should not exist
    And .kanbus.yml should have project_key "new"

  Scenario: Rekey preserves short ID hex suffixes
    Given a Kanbus project with key "apricitus"
    And an issue "apricitus-0a00f39c-34cf-4200-abcd-123456789012" exists
    When I run "kanbus rekey apricity"
    Then issue "apricity-0a00f39c" should resolve to "apricity-0a00f39c-34cf-4200-abcd-123456789012"

  Scenario: Rekey updates parent references
    Given a Kanbus project with key "old"
    And an issue "old-parent-1234-5678-abcd-123456789012abcd" exists with type "epic"
    And an issue "old-child-5678-9abc-abcd-123456789012abcd" exists with parent "old-parent-1234-5678-abcd-123456789012abcd"
    When I run "kanbus rekey new"
    Then issue "new-child-5678-9abc-abcd-123456789012abcd" should have parent "new-parent-1234-5678-abcd-123456789012abcd"

  Scenario: Rekey updates dependency references
    Given a Kanbus project with key "old"
    And an issue "old-task1-1234-5678-abcd-123456789012abcd" exists
    And an issue "old-task2-5678-9abc-abcd-123456789012abcd" exists
    And issue "old-task1-1234-5678-abcd-123456789012abcd" has dependency "blocked-by" on "old-task2-5678-9abc-abcd-123456789012abcd"
    When I run "kanbus rekey new"
    Then issue "new-task1-1234-5678-abcd-123456789012abcd" should have dependency "blocked-by" on "new-task2-5678-9abc-abcd-123456789012abcd"

  Scenario: Rekey rewrites ID mentions in issue descriptions
    Given a Kanbus project with key "old"
    And issues "old-issue1-1234-5678-abcd-123456789012ab" and "old-issue2-5678-9abc-abcd-123456789012ab" exist
    And issue "old-issue1-1234-5678-abcd-123456789012ab" has description "See old-issue2-5678-9abc-abcd-123456789012ab for details"
    When I run "kanbus rekey new"
    Then issue "new-issue1-1234-5678-abcd-123456789012ab" should have description "See new-issue2-5678-9abc-abcd-123456789012ab for details"

  Scenario: Rekey rewrites ID mentions in issue titles
    Given a Kanbus project with key "old"
    And issues "old-main-1234-5678-abcd-123456789012abcd" and "old-sub-5678-9abc-abcd-123456789012abcd" exist
    And issue "old-main-1234-5678-abcd-123456789012abcd" has title "Task for old-sub"
    When I run "kanbus rekey new"
    Then issue "new-main-1234-5678-abcd-123456789012abcd" should have title "Task for new-sub"

  Scenario: Rekey rewrites short ID mentions in descriptions
    Given a Kanbus project with key "old"
    And an issue "old-task-1234-5678-abcd-123456789012abcd" exists with description "See old-1a2b3c"
    And an issue "old-other-5678-9abc-abcd-123456789012abcd" exists
    When I run "kanbus rekey new"
    Then the rekey should succeed
    And issue "new-task-1234-5678-abcd-123456789012abcd" should have description "See new-1a2b3c"

  Scenario: Rekey ignores key mentions that are not valid issue IDs
    Given a Kanbus project with key "old"
    And an issue "old-task-1234-5678-abcd-123456789012abcd" exists with description "This is the old project documentation"
    When I run "kanbus rekey new"
    Then issue "new-task-1234-5678-abcd-123456789012abcd" should have description "This is the old project documentation"

  Scenario: Rekey rewrites ID mentions in comments
    Given a Kanbus project with key "old"
    And issues "old-issue1-1234-5678-abcd-123456789012ab" and "old-issue2-5678-9abc-abcd-123456789012ab" exist
    And issue "old-issue1-1234-5678-abcd-123456789012ab" has a comment "Related to old-issue2-5678-9abc-abcd-123456789012ab"
    When I run "kanbus rekey new"
    Then issue "new-issue1-1234-5678-abcd-123456789012ab" should have a comment "Related to new-issue2-5678-9abc-abcd-123456789012ab"

  Scenario: Rekey respects word boundaries for ID mentions
    Given a Kanbus project with key "old"
    And an issue "old-task-1234-5678-abcd-123456789012abcd" exists with description "See old-task-1234-5678-abcd-123456789012abcd now"
    When I run "kanbus rekey new"
    Then issue "new-task-1234-5678-abcd-123456789012abcd" should have description "See new-task-1234-5678-abcd-123456789012abcd now"

  Scenario: Rekey dry-run prints planned changes without modifying files
    Given a Kanbus project with key "old"
    And issues "old-issue1-1234-5678-abcd-123456789012ab" and "old-issue2-5678-9abc-abcd-123456789012ab" exist
    When I run "kanbus rekey new --dry-run"
    Then the command should succeed
    And stdout should contain "old-issue1-1234-5678-abcd-123456789012ab -> new-issue1-1234-5678-abcd-123456789012ab"
    And stdout should contain "old-issue2-5678-9abc-abcd-123456789012ab -> new-issue2-5678-9abc-abcd-123456789012ab"
    And issue "new-issue1-1234-5678-abcd-123456789012ab" should not exist
    And issue "old-issue1-1234-5678-abcd-123456789012ab" should still exist

  Scenario: Rekey dry-run counts text rewrites per issue
    Given a Kanbus project with key "old"
    And an issue "old-main-1234-5678-abcd-123456789012abcd" exists with title "old-sub" and description "old-sub"
    And an issue "old-sub-5678-9abc-abcd-123456789012abcd" exists
    When I run "kanbus rekey new --dry-run"
    Then stdout should contain "2 rewrites"

  Scenario: Rekey fails when new key equals old key
    Given a Kanbus project with key "same"
    And an issue "same-task-1234-5678-abcd-123456789012abcd" exists
    When I run "kanbus rekey same"
    Then the command should fail with exit code 1
    And stderr should contain "new key equals old key"
    And issue "same-task-1234-5678-abcd-123456789012abcd" should still exist

  Scenario: Rekey fails when new key is invalid
    Given a Kanbus project with key "old"
    And an issue "old-task-1234-5678-abcd-123456789012abcd" exists
    When I run "kanbus rekey invalid key"
    Then the command should fail with exit code 1
    And stderr should contain "invalid project key"
    And issue "old-task-1234-5678-abcd-123456789012abcd" should still exist

  Scenario: Rekey fails when target file already exists
    Given a Kanbus project with key "old"
    And an issue "old-task-1234-5678-abcd-123456789012abcd" exists
    And an issue "new-task-1234-5678-abcd-123456789012abcd" already exists
    When I run "kanbus rekey new"
    Then the command should fail with exit code 1
    And stderr should contain "already exists"
    And project key should still be "old"

  Scenario: Rekey fails when working tree has uncommitted changes
    Given a Kanbus project with key "old"
    And an issue "old-task-1234-5678-abcd-123456789012abcd" exists
    And the working tree has uncommitted changes under project/
    When I run "kanbus rekey new"
    Then the command should fail with exit code 1
    And stderr should contain "uncommitted changes"
    And project key should still be "old"

  Scenario: Rekey is idempotent
    Given a Kanbus project with key "old"
    And an issue "old-task-1234-5678-abcd-123456789012abcd" exists
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-task-1234-5678-abcd-123456789012abcd" should exist
    When I run "kanbus rekey new"
    Then the command should succeed with message "already rekeyed"
    And issue "new-task-1234-5678-abcd-123456789012abcd" should still exist

  Scenario: Rekey validation passes after completion
    Given a Kanbus project with key "old"
    And issues "old-task1-1234-5678-abcd-123456789012ab" and "old-task2-5678-9abc-abcd-123456789012ab" exist
    And issue "old-task1-1234-5678-abcd-123456789012ab" has parent "old-task2-5678-9abc-abcd-123456789012ab"
    When I run "kanbus rekey new"
    And I run "kanbus validate"
    Then the validate command should succeed

  Scenario: Rekey invalidates caches
    Given a Kanbus project with key "old"
    And issues "old-task-1234-5678-abcd-123456789012abcd" exists
    And a cache directory with index data exists
    When I run "kanbus rekey new"
    Then the cache directory should be invalidated or rebuilt

  Scenario: Rekey updates git history consistently
    Given a Kanbus project with key "old"
    And an issue "old-task-1234-5678-abcd-123456789012abcd" exists
    When I run "kanbus rekey new"
    And I check the git history
    Then the event history should reflect the rekey operation
