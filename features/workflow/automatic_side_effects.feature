Feature: Automatic side effects on status transitions

  Scenario: Closing an issue sets closed_at timestamp
    Given a Kanbus project with default configuration
    And an issue "kanbus-test01" of type "task" with status "open"
    And issue "kanbus-test01" has no closed_at timestamp
    When I run "kanbus update kanbus-test01 --status closed"
    Then issue "kanbus-test01" should have a closed_at timestamp

  Scenario: Reopening an issue clears closed_at timestamp
    Given a Kanbus project with default configuration
    And an issue "kanbus-test01" of type "task" with status "closed"
    And issue "kanbus-test01" has a closed_at timestamp
    When I run "kanbus update kanbus-test01 --status open"
    Then issue "kanbus-test01" should have no closed_at timestamp
