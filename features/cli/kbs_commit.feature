Feature: Commit project issues to git
  As a Kanbus user
  I want to commit board state (issues and events) to git
  So that board state is persisted without manual git rituals

  Scenario: Commit stages and commits project/issues changes
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Old Title"
    When I run "kanbus update kanbus-aaa --title \"New Title\""
    And I run "kanbus commit"
    Then the command should succeed
    And stdout should contain "Committed project/issues and project/events"
    And project/issues should be committed to git
    And the events directory should be committed to git
    And the last commit message should be "chore(kanbus): commit board state"

  Scenario: Commit includes events written by comment and close
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Old Title"
    When I run "kanbus comment kanbus-aaa \"Progress note\""
    And I run "kanbus close kanbus-aaa"
    Then the events directory should contain event files
    When I run "kanbus commit"
    Then the command should succeed
    And project/issues should be committed to git
    And the events directory should be committed to git

  Scenario: Commit leaves events out when events are turned off
    Given a Kanbus project with default configuration
    And the Kanbus configuration disables events
    And an issue "kanbus-aaa" exists with title "Old Title"
    When I run "kanbus update kanbus-aaa --title \"New Title\""
    And I run "kanbus comment kanbus-aaa \"Progress note\""
    And I run "kanbus close kanbus-aaa"
    And I run "kanbus commit"
    Then the command should succeed
    And stdout should contain "Committed project/issues"
    And stdout should not contain "project/events"
    And the events directory should contain no event files
    And project/issues should be committed to git

  Scenario: Creating an issue writes no events when events are turned off
    Given a Kanbus project with default configuration
    And the Kanbus configuration disables events
    When I run "kanbus create Example --type task"
    Then the command should succeed
    And the events directory should contain no event files

  Scenario: Commit succeeds when nothing to commit
    Given a Kanbus project with default configuration
    When I run "kanbus commit"
    And I run "kanbus commit"
    Then the command should succeed
    And stdout should contain "Nothing to commit"

  Scenario: Commit fails outside a git repository
    Given a directory that is not a git repository
    When I run "kanbus commit"
    Then the command should fail with exit code 1
    And stderr should contain "not a git repository"
