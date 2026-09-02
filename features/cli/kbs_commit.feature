Feature: Commit project issues to git
  As a Kanbus user
  I want to commit project/issues to git
  So that board state is persisted without manual git rituals

  Scenario: Commit stages and commits project/issues changes
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Old Title"
    When I run "kanbus update kanbus-aaa --title \"New Title\""
    And I run "kanbus commit"
    Then the command should succeed
    And stdout should contain "Committed project/issues"
    And project/issues should be committed to git

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
