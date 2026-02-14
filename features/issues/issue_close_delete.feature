Feature: Issue close and delete

  Scenario: Close an issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with status "open"
    When I run "kanbus close kanbus-aaa"
    Then the command should succeed
    And stdout should contain "Closed kanbus-aaa"
    And issue "kanbus-aaa" should have status "closed"
    And issue "kanbus-aaa" should have a closed_at timestamp

  Scenario: Close missing issue fails
    Given a Kanbus project with default configuration
    When I run "kanbus close kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Delete an issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    When I run "kanbus delete kanbus-aaa"
    Then the command should succeed
    And stdout should contain "Deleted kanbus-aaa"
    And issue "kanbus-aaa" should not exist

  Scenario: Delete missing issue fails
    Given a Kanbus project with default configuration
    When I run "kanbus delete kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"
