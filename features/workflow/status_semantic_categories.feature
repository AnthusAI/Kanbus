Feature: Status semantic categories

  Scenario: Claiming resolves the in_progress semantic category to a custom status key
    Given a Kanbus project with default configuration
    And the primary in_progress status key is configured as "doing"
    And an issue "kanbus-test01" of type "task" with status "open"
    And the current user is "dev@example.com"
    When I run "kanbus update kanbus-test01 --claim"
    Then issue "kanbus-test01" should have status "doing"
    And issue "kanbus-test01" should have assignee "dev@example.com"
