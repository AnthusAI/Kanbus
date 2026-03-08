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

  Scenario: Description updates emit field_updated events
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Standalone Task --type task --description 'Initial description'"
    And I capture the issue identifier
    When I update the last issue description to "Updated description"
    Then the event log for the last issue should include a field update for "description" from "Initial description" to "Updated description"

  Scenario: Assignee updates emit field_updated events
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Standalone Task --type task --assignee dev@example.com"
    And I capture the issue identifier
    When I update the last issue assignee to "owner@example.com"
    Then the event log for the last issue should include a field update for "assignee" from "dev@example.com" to "owner@example.com"

  Scenario: Priority updates emit field_updated events
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Standalone Task --type task --priority 2"
    And I capture the issue identifier
    When I update the last issue priority to 1
    Then the event log for the last issue should include a priority update from 2 to 1

  Scenario: Label updates emit field_updated events
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Standalone Task --type task --label alpha --label beta"
    And I capture the issue identifier
    When I set labels on the last issue to "beta,gamma"
    Then the event log for the last issue should include a labels update from "alpha,beta" to "beta,gamma"

  Scenario: Localize emits issue_localized events
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I localize the last issue
    Then the event log for the last issue should include a transfer event "issue_localized" from "shared" to "local"

  Scenario: Promote emits issue_promoted events
    Given a Kanbus project with default configuration
    When I run the command "kanbus create --local Local task"
    And I capture the issue identifier
    When I promote the last issue
    Then the event log for the last issue should include a transfer event "issue_promoted" from "local" to "shared"

  Scenario: Comment events record ids but not text
    Given a Kanbus project with default configuration
    And the current user is "dev@example.com"
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I add a comment to the last issue with text "First comment"
    Then the event log for the last issue should include a comment_added event by "dev@example.com" with a comment id
    And the event log for the last issue should not include comment text

  Scenario: Comment updates emit comment_updated events
    Given a Kanbus project with default configuration
    And the current user is "dev@example.com"
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I add a comment to the last issue with text "First comment"
    And I update the last issue comment to "Updated comment"
    Then the event log for the last issue should include a comment_updated event by "dev@example.com" with the last comment id
    And the event log for the last issue should not include comment text

  Scenario: Comment deletion emits comment_deleted events
    Given a Kanbus project with default configuration
    And the current user is "dev@example.com"
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I add a comment to the last issue with text "First comment"
    And I delete the last issue comment
    Then the event log for the last issue should include a comment_deleted event by "dev@example.com" with the last comment id
    And the event log for the last issue should not include comment text

  Scenario: Dependency events record target ids
    Given a Kanbus project with default configuration
    And an issue "kanbus-dep-target" exists
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I add a blocked-by dependency from the last issue to "kanbus-dep-target"
    Then the event log for the last issue should include a dependency "blocked-by" on "kanbus-dep-target"

  Scenario: Dependency removal emits dependency_removed events
    Given a Kanbus project with default configuration
    And an issue "kanbus-dep-target" exists
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I add a blocked-by dependency from the last issue to "kanbus-dep-target"
    And I remove the blocked-by dependency from the last issue to "kanbus-dep-target"
    Then the event log for the last issue should include a dependency_removed "blocked-by" on "kanbus-dep-target"

  Scenario: Deleting an issue emits issue_deleted event
    Given a Kanbus project with default configuration
    When I run the command "kanbus create Standalone Task --type task"
    And I capture the issue identifier
    When I delete the last issue
    Then the event log for the last issue should include event type "issue_deleted"
