Feature: Claim workflow

  Scenario: Claiming an issue sets assignee and transitions to in_progress
    Given a Taskulus project with default configuration
    And an issue "tsk-test01" of type "task" with status "open"
    And the current user is "dev@example.com"
    When I run "tsk update tsk-test01 --claim"
    Then issue "tsk-test01" should have status "in_progress"
    And issue "tsk-test01" should have assignee "dev@example.com"
