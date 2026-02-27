Feature: Policy rejection behavior
  As a project manager
  I want clear error messages when policies fail
  So that users understand what rule was violated

  Scenario: Error message includes policy file name
    Given a Kanbus project with default configuration
    And a policy file "my-custom-rule.policy" with content:
      """
      Feature: Custom rule
        Scenario: Test
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus update kanbus-test01 --title "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "my-custom-rule.policy"

  Scenario: Error message includes scenario name
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Very specific scenario name
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus update kanbus-test01 --title "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "Very specific scenario name"

  Scenario: Error message includes failed step
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Test
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus update kanbus-test01 --title "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "Then the issue must have field \"assignee\""

  Scenario: First failing policy stops evaluation
    Given a Kanbus project with default configuration
    And a policy file "first.policy" with content:
      """
      Feature: First
        Scenario: Check assignee
          Then the issue must have field "assignee"
      """
    And a policy file "second.policy" with content:
      """
      Feature: Second
        Scenario: Check description
          Then the description must not be empty
      """
    And an issue "kanbus-test01" of type "task" with status "open" and description ""
    When I run "kanbus update kanbus-test01 --title "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "policy violation"

  Scenario: Issue state is not modified when policy fails
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Require assignee
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open" and title "Original Title"
    When I run "kanbus update kanbus-test01 --title "New Title""
    Then the command should fail with exit code 1
    And issue "kanbus-test01" should have title "Original Title"
    And issue "kanbus-test01" should have status "open"
