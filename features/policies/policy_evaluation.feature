Feature: Policy evaluation
  As a project manager
  I want policies to be evaluated before issue transitions
  So that project rules are automatically enforced

  Scenario: Policy passes and transition succeeds
    Given a Kanbus project with default configuration
    And a policy file "require-assignee.policy" with content:
      """
      Feature: Tasks require assignee

        Scenario: Task must have assignee to start
          Given the issue type is "task"
          When transitioning to "in_progress"
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus update kanbus-test01 --status in_progress --assignee alice@example.com"
    Then the command should succeed
    And issue "kanbus-test01" should have status "in_progress"
    And issue "kanbus-test01" should have assignee "alice@example.com"

  Scenario: Policy fails and transition is rejected
    Given a Kanbus project with default configuration
    And a policy file "require-assignee.policy" with content:
      """
      Feature: Tasks require assignee

        Scenario: Task must have assignee to start
          Given the issue type is "task"
          When transitioning to "in_progress"
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus update kanbus-test01 --status in_progress"
    Then the command should fail with exit code 1
    And stderr should not contain "Traceback"
    And stderr should contain "policy violation"
    And stderr should contain "require-assignee.policy"
    And stderr should contain "issue must have field"
    And issue "kanbus-test01" should have status "open"

  Scenario: Multiple policies are evaluated
    Given a Kanbus project with default configuration
    And a policy file "require-assignee.policy" with content:
      """
      Feature: Tasks require assignee

        Scenario: Task must have assignee to start
          Given the issue type is "task"
          When transitioning to "in_progress"
          Then the issue must have field "assignee"
      """
    And a policy file "require-description.policy" with content:
      """
      Feature: Tasks require description

        Scenario: Task must have description
          Given the issue type is "task"
          Then the description must not be empty
      """
    And an issue "kanbus-test01" of type "task" with status "open" and description ""
    When I run "kanbus update kanbus-test01 --status in_progress --assignee alice@example.com"
    Then the command should fail with exit code 1
    And stderr should not contain "Traceback"
    And stderr should contain "policy violation"
    And stderr should contain "require-description.policy"
    And stderr should contain "description is empty"

  Scenario: No policies directory means no enforcement
    Given a Kanbus project with default configuration
    And no policies directory exists
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus update kanbus-test01 --status in_progress"
    Then the command should succeed
    And issue "kanbus-test01" should have status "in_progress"

  Scenario: Empty policies directory means no enforcement
    Given a Kanbus project with default configuration
    And an empty policies directory exists
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus update kanbus-test01 --status in_progress"
    Then the command should succeed
    And issue "kanbus-test01" should have status "in_progress"
