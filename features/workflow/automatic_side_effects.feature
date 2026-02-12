Feature: Automatic side effects on status transitions

  Scenario: Closing an issue sets closed_at timestamp
    Given a Taskulus project with default configuration
    And an issue "tsk-test01" of type "task" with status "open"
    And issue "tsk-test01" has no closed_at timestamp
    When I run "tsk update tsk-test01 --status closed"
    Then issue "tsk-test01" should have a closed_at timestamp

  Scenario: Reopening an issue clears closed_at timestamp
    Given a Taskulus project with default configuration
    And an issue "tsk-test01" of type "task" with status "closed"
    And issue "tsk-test01" has a closed_at timestamp
    When I run "tsk update tsk-test01 --status open"
    Then issue "tsk-test01" should have no closed_at timestamp
