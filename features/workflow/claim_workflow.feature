Feature: Claim workflow

  Scenario: Claiming an issue sets assignee and transitions to in_progress
    Given a Kanbus project with default configuration
    And an issue "kanbus-test01" of type "task" with status "open"
    And the current user is "dev@example.com"
    When I run "kanbus update kanbus-test01 --claim"
    Then issue "kanbus-test01" should have status "in_progress"
    And issue "kanbus-test01" should have assignee "dev@example.com"
