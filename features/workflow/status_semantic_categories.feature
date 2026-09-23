Feature: Status semantic categories

  Scenario: Claiming resolves the in_progress semantic category to a custom status key
    Given a Kanbus project with default configuration
    And the primary in_progress status key is configured as "doing"
    And an issue "kanbus-test01" of type "task" with status "open"
    And the current user is "dev@example.com"
    When I run "kanbus update kanbus-test01 --claim"
    Then issue "kanbus-test01" should have status "doing"
    And issue "kanbus-test01" should have assignee "dev@example.com"

  Scenario: A configuration that predates semantic categories still loads
    Given a Kanbus project with default configuration
    And the configuration omits every semantic category and adds the status "published"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "published" should have semantic category "done"
    And the configured status "open" should have semantic category "todo"
    And the configured status "in_progress" should have semantic category "in_progress"
    And the configured status "closed" should have semantic category "done"

  Scenario: A custom stage without a semantic category is treated as in progress
    Given a Kanbus project with default configuration
    And the configuration omits every semantic category and adds the status "copywriting"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "copywriting" should have semantic category "in_progress"

  Scenario: An explicit semantic category is never overridden by the derived one
    Given a Kanbus project with default configuration
    And the configuration adds the status "published" with semantic category "todo"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "published" should have semantic category "todo"
