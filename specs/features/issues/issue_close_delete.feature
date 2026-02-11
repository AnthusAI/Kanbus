Feature: Issue close and delete

  Scenario: Close an issue
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists with status "open"
    When I run "tsk close tsk-aaa"
    Then the command should succeed
    And issue "tsk-aaa" should have status "closed"
    And issue "tsk-aaa" should have a closed_at timestamp

  Scenario: Close missing issue fails
    Given a Taskulus project with default configuration
    When I run "tsk close tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Delete an issue
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists
    When I run "tsk delete tsk-aaa"
    Then the command should succeed
    And issue "tsk-aaa" should not exist

  Scenario: Delete missing issue fails
    Given a Taskulus project with default configuration
    When I run "tsk delete tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"
