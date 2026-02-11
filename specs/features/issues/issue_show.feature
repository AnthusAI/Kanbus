Feature: Issue display

  Scenario: Show issue details
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists with title "Implement OAuth2 flow"
    And issue "tsk-aaa" has status "open" and type "task"
    When I run "tsk show tsk-aaa"
    Then the command should succeed
    And stdout should contain "Implement OAuth2 flow"
    And stdout should contain "open"
    And stdout should contain "task"

  Scenario: Show issue as JSON
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists with title "Implement OAuth2 flow"
    When I run "tsk show tsk-aaa --json"
    Then the command should succeed
    And stdout should contain "\"id\": \"tsk-aaa\""
    And stdout should contain "\"title\": \"Implement OAuth2 flow\""

  Scenario: Show missing issue
    Given a Taskulus project with default configuration
    When I run "tsk show tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"
