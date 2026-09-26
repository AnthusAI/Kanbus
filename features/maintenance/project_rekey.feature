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
    And a "task" issue "apricitus-0a1b2c3d-4e5f-4a1b-8c2d-3e4f5a6b7c8d" exists
    And the project is committed to git
    When I run "kanbus rekey apricity"
    And I run "kanbus show apricity-0a1b2c"
    Then the command should succeed

  Scenario: Rekey updates parent references
    Given a Kanbus project with key "old"
    And an "epic" issue "old-parent01-1234-5678-abcd-123456789012" exists
    And a "task" issue "old-child001-1234-5678-abcd-123456789012" exists
    And issue "old-child001-1234-5678-abcd-123456789012" has parent "old-parent01-1234-5678-abcd-123456789012"
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-child001-1234-5678-abcd-123456789012" should have parent "new-parent01-1234-5678-abcd-123456789012"

  Scenario: Rekey updates dependency references
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0001-1234-5678-abcd-123456789012" exists
    And a "task" issue "old-task0002-5678-9abc-abcd-123456789012" exists
    And issue "old-task0001-1234-5678-abcd-123456789012" is blocked by "old-task0002-5678-9abc-abcd-123456789012"
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-task0001-1234-5678-abcd-123456789012" should be blocked by "new-task0002-5678-9abc-abcd-123456789012"

  Scenario: Rekey changes only the top-level project key in .kanbus.yml
    Given a Kanbus project with key "old"
    And .kanbus.yml ends with the comment "# keep this comment"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And .kanbus.yml should have project_key "new"
    And .kanbus.yml should contain "# keep this comment"
    When I run "kanbus list"
    Then the command should succeed

  Scenario: Rekey rewrites ID mentions in issue descriptions
    Given a Kanbus project with key "old"
    And a "task" issue "old-issue01-1234-5678-abcd-123456789012" exists
    And issue "old-issue01-1234-5678-abcd-123456789012" has description "See old-issue02-1234-5678-abcd-123456789012 for details"
    And a "task" issue "old-issue02-1234-5678-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-issue01-1234-5678-abcd-123456789012" should have description "See new-issue02-1234-5678-abcd-123456789012 for details"

  Scenario: Rekey rewrites ID mentions in issue titles
    Given a Kanbus project with key "old"
    And an issue "old-main0000-1234-5678-abcd-123456789012" exists with title "Task for old-sub00000-5678-9abc-abcd-123456789012"
    And a "task" issue "old-sub00000-5678-9abc-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-main0000-1234-5678-abcd-123456789012" should have title "Task for new-sub00000-5678-9abc-abcd-123456789012"

  Scenario: Rekey rewrites short ID mentions in descriptions when they resolve
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And issue "old-task0000-1234-5678-abcd-123456789012" has description "See old-1a2b3c for details"
    And a "task" issue "old-1a2b3c00-1234-5678-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-task0000-1234-5678-abcd-123456789012" should have description "See new-1a2b3c for details"

  Scenario: Rekey ignores short ID mentions that don't resolve
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And issue "old-task0000-1234-5678-abcd-123456789012" has description "See old-nomatch for details"
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-task0000-1234-5678-abcd-123456789012" should have description "See old-nomatch for details"

  Scenario: Rekey ignores key mentions that are not valid issue IDs
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And issue "old-task0000-1234-5678-abcd-123456789012" has description "This is the old project documentation"
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-task0000-1234-5678-abcd-123456789012" should have description "This is the old project documentation"

  Scenario: Rekey rewrites ID mentions in comments
    Given a Kanbus project with key "old"
    And a "task" issue "old-issue01-1234-5678-abcd-123456789012" exists
    And a "task" issue "old-issue02-5678-9abc-abcd-123456789012" exists
    And issue "old-issue01-1234-5678-abcd-123456789012" has a comment "Related to old-issue02-5678-9abc-abcd-123456789012"
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-issue01-1234-5678-abcd-123456789012" should have a comment "Related to new-issue02-5678-9abc-abcd-123456789012"

  Scenario: Rekey respects word boundaries for ID mentions
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And issue "old-task0000-1234-5678-abcd-123456789012" has description "See old-task0000-1234-5678-abcd-123456789012 now"
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-task0000-1234-5678-abcd-123456789012" should have description "See new-task0000-1234-5678-abcd-123456789012 now"

  Scenario: Rekey dry-run prints planned changes without modifying files
    Given a Kanbus project with key "old"
    And a "task" issue "old-issue01-1234-5678-abcd-123456789012" exists
    And a "task" issue "old-issue02-5678-9abc-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey new --dry-run"
    Then the command should succeed
    And stdout should contain "old-issue01-1234-5678-abcd-123456789012 -> new-issue01-1234-5678-abcd-123456789012"
    And stdout should contain "old-issue02-5678-9abc-abcd-123456789012 -> new-issue02-5678-9abc-abcd-123456789012"
    And issue "new-issue01-1234-5678-abcd-123456789012" should not exist
    And issue "old-issue01-1234-5678-abcd-123456789012" should exist

  Scenario: Rekey fails when new key is invalid
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey Bad_Key!"
    Then the command should fail with exit code 1
    And stderr should contain "invalid project key"
    And issue "old-task0000-1234-5678-abcd-123456789012" should exist

  Scenario: Rekey fails when target file already exists
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And a "task" issue "new-task0000-1234-5678-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should fail with exit code 1
    And stderr should contain "already exists"
    And .kanbus.yml should have project_key "old"

  Scenario: Rekey fails when working tree has uncommitted changes
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And the project is committed to git
    And the project directory has uncommitted changes
    When I run "kanbus rekey new"
    Then the command should fail with exit code 1
    And stderr should contain "uncommitted changes"
    And .kanbus.yml should have project_key "old"

  Scenario: Rekey is idempotent
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey new"
    Then the command should succeed
    And issue "new-task0000-1234-5678-abcd-123456789012" should exist
    When I run "kanbus rekey new"
    Then the command should succeed
    And stderr should contain "already"
    And issue "new-task0000-1234-5678-abcd-123456789012" should exist

  Scenario: Rekey validation passes after completion
    Given a Kanbus project with key "old"
    And an "epic" issue "old-parent01-1234-5678-abcd-123456789012" exists
    And a "task" issue "old-task2000-5678-9abc-abcd-123456789012" exists
    And issue "old-task2000-5678-9abc-abcd-123456789012" has parent "old-parent01-1234-5678-abcd-123456789012"
    And the project is committed to git
    When I run "kanbus rekey new"
    And I run "kanbus validate"
    Then the command should succeed

  Scenario: Rekey allows immediate list and show after completion
    Given a Kanbus project with key "old"
    And a "task" issue "old-task0000-1234-5678-abcd-123456789012" exists
    And the project is committed to git
    When I run "kanbus rekey new"
    And I run "kanbus show new-task0000-1234-5678-abcd-123456789012"
    Then the command should succeed
    And stdout should contain "new-task00"
    When I run "kanbus show old-task0000-1234-5678-abcd-123456789012"
    Then the command should fail with exit code 1
    When I run "kanbus list"
    Then the command should succeed
