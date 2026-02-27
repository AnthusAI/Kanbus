Feature: Policy steps library
  As a policy author
  I want a comprehensive library of built-in steps
  So that I can express project rules clearly

  Scenario: Then step - issue must have field
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Check field
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus update kanbus-test01 --title "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "issue does not have field"

  @skip
  Scenario: Then step - issue must not have field
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Check field absence
          Then the issue must not have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open" and assignee "alice@example.com"
    When I run "kanbus update kanbus-test01 --title "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "issue has field"

  Scenario: Then step - field must be value
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Check field value
          Then the field "status" must be "open"
      """
    And an issue "kanbus-test01" of type "task" with status "in_progress"
    When I run "kanbus update kanbus-test01 --title "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "field \"status\" is \"in_progress\" but must be \"open\""

  @skip
  Scenario: Then step - all children must have status
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Check children status
          Given the issue type is "epic"
          When transitioning to "closed"
          Then all child issues must have status "closed"
      """
    And an issue "kanbus-epic01" of type "epic" with status "in_progress"
    And an issue "kanbus-task01" of type "task" with status "in_progress" and parent "kanbus-epic01"
    When I run "kanbus update kanbus-epic01 --status closed"
    Then the command should fail with exit code 1
    And stderr should contain "child issues"
    And stderr should contain "do not have status"

  @skip
  Scenario: Then step - no children may have status
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Check no children blocked
          Given the issue type is "epic"
          Then no child issues may have status "blocked"
      """
    And an issue "kanbus-epic01" of type "epic" with status "in_progress"
    And an issue "kanbus-task01" of type "task" with status "blocked" and parent "kanbus-epic01"
    When I run "kanbus update kanbus-epic01 --title "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "child issues"
    And stderr should contain "have status \"blocked\" but should not"

  @skip
  Scenario: Then step - parent must have status
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Parent must be active
          Given the issue has a parent
          When transitioning to "in_progress"
          Then the parent issue must have status "in_progress"
      """
    And an issue "kanbus-epic01" of type "epic" with status "open"
    And an issue "kanbus-task01" of type "task" with status "open" and parent "kanbus-epic01"
    When I run "kanbus update kanbus-task01 --status in_progress"
    Then the command should fail with exit code 1
    And stderr should contain "parent issue"
    And stderr should contain "must have status"

  @skip
  Scenario: Then step - issue must have at least N labels
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Require labels
          When transitioning to "closed"
          Then the issue must have at least 2 labels
      """
    And an issue "kanbus-test01" of type "task" with status "in_progress" and labels "bug"
    When I run "kanbus update kanbus-test01 --status closed"
    Then the command should fail with exit code 1
    And stderr should contain "has 1 label(s) but must have at least 2"

  Scenario: Then step - issue must have specific label
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Require reviewed label
          When transitioning to "closed"
          Then the issue must have label "reviewed"
      """
    And an issue "kanbus-test01" of type "task" with status "in_progress"
    When I run "kanbus update kanbus-test01 --status closed"
    Then the command should fail with exit code 1
    And stderr should contain "does not have label \"reviewed\""

  Scenario: Then step - description must not be empty
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Require description
          Given the issue type is "task"
          Then the description must not be empty
      """
    And an issue "kanbus-test01" of type "task" with status "open" and description ""
    When I run "kanbus update kanbus-test01 --title "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "description is empty"

  Scenario: Then step - title must match pattern
    Given a Kanbus project with default configuration
    And a policy file "test.policy" with content:
      """
      Feature: Test
        Scenario: Require ticket prefix
          Given the issue type is "bug"
          Then the title must match pattern "^BUG-"
      """
    And an issue "kanbus-bug01" of type "bug" with status "open" and title "Fix login issue"
    When I run "kanbus update kanbus-bug01 --description "Updated""
    Then the command should fail with exit code 1
    And stderr should contain "does not match pattern"
