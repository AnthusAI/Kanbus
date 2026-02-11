@wip
Feature: Issue ID generation
  As a Taskulus user
  I want issue IDs that are unique and predictable
  So that I can reference issues reliably

  @wip
  Scenario: Generated IDs follow the prefix-hex format
    Given a project with prefix "tsk"
    When I generate an issue ID
    Then the ID should match the pattern "tsk-[0-9a-f]{6}"

  @wip
  Scenario: Generated IDs are unique across multiple creations
    Given a project with prefix "tsk"
    When I generate 100 issue IDs
    Then all 100 IDs should be unique

  @wip
  Scenario: ID generation handles collision with existing issues
    Given a project with an existing issue "tsk-aaaaaa"
    And the hash function would produce "aaaaaa" for the next issue
    When I generate an issue ID
    Then the ID should not be "tsk-aaaaaa"
    And the ID should match the pattern "tsk-[0-9a-f]{6}"
