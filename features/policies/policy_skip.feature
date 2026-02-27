Feature: Policy scenario skipping
  As a policy author
  I want scenarios to skip when Given/When conditions don't match
  So that policies only apply to relevant situations

  Scenario: Scenario skipped when issue type doesn't match
    Given a Kanbus project with default configuration
    And a policy file "task-only.policy" with content:
      """
      Feature: Task-specific policy

        Scenario: Only tasks need assignee
          Given the issue type is "task"
          When transitioning to "in_progress"
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-epic01" of type "epic" with status "open"
    When I run "kanbus update kanbus-epic01 --status in_progress"
    Then the command should succeed
    And issue "kanbus-epic01" should have status "in_progress"

  Scenario: Scenario skipped when transition doesn't match
    Given a Kanbus project with default configuration
    And a policy file "start-only.policy" with content:
      """
      Feature: Start transition policy

        Scenario: Assignee required when starting
          When transitioning to "in_progress"
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "in_progress"
    When I run "kanbus update kanbus-test01 --status closed"
    Then the command should succeed
    And issue "kanbus-test01" should have status "closed"

  Scenario: Scenario applies when all Given/When conditions match
    Given a Kanbus project with default configuration
    And a policy file "specific.policy" with content:
      """
      Feature: Specific policy

        Scenario: Task starting from open needs assignee
          Given the issue type is "task"
          When transitioning from "open" to "in_progress"
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus update kanbus-test01 --status in_progress"
    Then the command should fail with exit code 1
    And stderr should contain "policy violation"

  Scenario: Multiple Given conditions all must match
    Given a Kanbus project with default configuration
    And a policy file "compound.policy" with content:
      """
      Feature: Compound conditions

        Scenario: High priority tasks need description
          Given the issue type is "task"
          Given the issue priority is 1
          Then the description must not be empty
      """
    And an issue "kanbus-test01" of type "task" with status "open" and priority 2 and description ""
    When I run "kanbus update kanbus-test01 --title "Updated title""
    Then the command should succeed

  @skip
  Scenario: Scenario applies when all compound Given conditions match
    Given a Kanbus project with default configuration
    And a policy file "compound.policy" with content:
      """
      Feature: Compound conditions

        Scenario: High priority tasks need description
          Given the issue type is "task"
          Given the issue priority is 1
          Then the description must not be empty
      """
    And an issue "kanbus-test01" of type "task" with status "open" and priority 1 and description ""
    When I run "kanbus update kanbus-test01 --title "Updated title""
    Then the command should fail with exit code 1
    And stderr should contain "policy violation"
    And stderr should contain "description is empty"
