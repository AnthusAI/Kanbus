Feature: Event history
  As a Kanbus user
  I want issue actions to be recorded as events
  So that history is auditable and UI can display timelines

  Scenario: Issue creation emits issue_created event
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Implement OAuth2 flow"
    And I capture the issue identifier
    Then the event log for the last issue should include event type "issue_created"
    And the event log filenames for the last issue should be ISO timestamped

  Scenario: Status updates emit state transition events
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I update the last issue status to "in_progress"
    Then the event log for the last issue should include a state transition from "open" to "in_progress"

  Scenario: Field updates emit field_updated events
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I update the last issue title to "Updated title"
    Then the event log for the last issue should include a field update for "title" from "Standalone Task" to "Updated title"

  Scenario: Comment events record ids but not text
    Given a Kanbus project with default configuration
    And the current user is "dev@example.com"
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I add a comment to the last issue with text "First comment"
    Then the event log for the last issue should include a comment_added event by "dev@example.com" with a comment id
    And the event log for the last issue should not include comment text

  Scenario: Dependency events record target ids
    Given a Kanbus project with default configuration
    And an issue "kanbus-dep-target" exists
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I add a blocked-by dependency from the last issue to "kanbus-dep-target"
    Then the event log for the last issue should include a dependency "blocked-by" on "kanbus-dep-target"

  Scenario: Deleting an issue emits issue_deleted event
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I delete the last issue
    Then the event log for the last issue should include event type "issue_deleted"
