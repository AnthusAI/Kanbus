Feature: Issue creation

  Scenario: Create a basic task with defaults
    Given a Taskulus project with default configuration
    When I run "tsk create Implement OAuth2 flow"
    Then the command should succeed
    And stdout should contain a valid issue ID
    And an issue file should be created in the issues directory
    And the created issue should have title "Implement OAuth2 flow"
    And the created issue should have type "task"
    And the created issue should have status "open"
    And the created issue should have priority 2
    And the created issue should have an empty labels list
    And the created issue should have an empty dependencies list
    And the created issue should have a created_at timestamp
    And the created issue should have an updated_at timestamp

  Scenario: Create an issue with all options specified
    Given a Taskulus project with default configuration
    And an "epic" issue "tsk-epic01" exists
    When I run "tsk create Fix login bug --type bug --priority 1 --assignee dev@example.com --parent tsk-epic01 --label auth --label urgent --description \"Bug in login\""
    Then the command should succeed
    And the created issue should have type "bug"
    And the created issue should have priority 1
    And the created issue should have assignee "dev@example.com"
    And the created issue should have parent "tsk-epic01"
    And the created issue should have labels "auth, urgent"
    And the created issue should have description "Bug in login"

  Scenario: Create an issue with invalid type
    Given a Taskulus project with default configuration
    When I run "tsk create Bad Issue --type nonexistent"
    Then the command should fail with exit code 1
    And stderr should contain "unknown issue type"

  Scenario: Create an issue with nonexistent parent
    Given a Taskulus project with default configuration
    When I run "tsk create Orphan --parent tsk-nonexistent"
    Then the command should fail with exit code 1
    And stderr should contain "not found"
