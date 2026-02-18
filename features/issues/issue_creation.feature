Feature: Issue creation

  Scenario: Create a basic task with defaults
    Given a Kanbus project with default configuration
    When I run "kanbus create Implement OAuth2 flow"
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

  Scenario: Create uses default assignee from configuration
    Given a Kanbus project with default configuration
    And the Kanbus configuration sets default assignee "dev@example.com"
    When I run "kanbus create Implement OAuth2 flow"
    Then the command should succeed
    And the created issue should have assignee "dev@example.com"

  Scenario: Create an issue with all options specified
    Given a Kanbus project with default configuration
    And an "epic" issue "kanbus-epic01" exists
    When I run "kanbus create Fix login bug --type bug --priority 1 --assignee dev@example.com --parent kanbus-epic01 --label auth --label urgent --description \"Bug in login\""
    Then the command should succeed
    And the created issue should have type "bug"
    And the created issue should have priority 1
    And the created issue should have assignee "dev@example.com"
    And the created issue should have parent "kanbus-epic01"
    And the created issue should have labels "auth, urgent"
    And the created issue should have description "Bug in login"

  Scenario: Create an issue with invalid type
    Given a Kanbus project with default configuration
    When I run "kanbus create Bad Issue --type nonexistent"
    Then the command should fail with exit code 1
    And stderr should contain "unknown issue type"

  Scenario: Create fails with invalid initial status
    Given a Kanbus project with an invalid configuration containing unknown initial status
    When I run "kanbus create Implement OAuth2 flow"
    Then the command should fail with exit code 1
    And stderr should contain "initial_status"

  Scenario: Create fails when status validation rejects initial status
    Given a Kanbus project with default configuration
    And issue creation status validation fails
    When I run "kanbus create Implement OAuth2 flow"
    Then the command should fail with exit code 1
    And stderr should contain "unknown status"

  Scenario: Create bypasses validation with --no-validate
    Given a Kanbus project with default configuration
    And an "epic" issue "kanbus-epic01" exists
    When I run "kanbus create Bad Parent --type epic --parent kanbus-epic01 --no-validate"
    Then the command should succeed

  Scenario: Create an issue with invalid priority
    Given a Kanbus project with default configuration
    When I run "kanbus create Bad Priority --priority 99"
    Then the command should fail with exit code 1
    And stderr should contain "invalid priority"

  Scenario: Create an issue with nonexistent parent
    Given a Kanbus project with default configuration
    When I run "kanbus create Orphan --parent kanbus-nonexistent"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Create an issue without a title
    Given a Kanbus project with default configuration
    When I run "kanbus create"
    Then the command should fail with exit code 1
    And stderr should contain "title is required"

  Scenario: Create fails without a project
    Given an empty git repository
    When I run "kanbus create Standalone Task --type task"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Create fails with invalid configuration
    Given a Kanbus project with an invalid configuration containing unknown fields
    When I run "kanbus create Implement OAuth2 flow"
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  Scenario: Create fails when configuration path lookup fails
    Given a Kanbus project with default configuration
    And configuration path lookup will fail
    When I create an issue directly with title "Implement OAuth2 flow"
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

  Scenario: Create ignores non-issue files in the issues directory
    Given a Kanbus project with default configuration
    And a non-issue file exists in the issues directory
    When I run "kanbus create Implement OAuth2 flow"
    Then the command should succeed

  Scenario: Create fails when title already exists in shared issues
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Implement OAuth2 flow"
    When I run "kanbus create implement oauth2 flow"
    Then the command should fail with exit code 1
    And stderr should contain "duplicate title"
    And stderr should contain "kanbus-aaa"
    And the issues directory should contain 1 issue file
