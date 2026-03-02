Feature: Issue move command
  As a project manager
  I want to move issues between types
  So that I can correct issue classification without manual file edits

  Scenario: Move changes issue type
    Given a Kanbus project with default configuration
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus move kanbus-test01 bug"
    Then the command should succeed
    And stdout should contain "Moved kanbus-test01 to type bug"
    And issue "kanbus-test01" should have type "bug"

  Scenario: Move rejects unknown issue type
    Given a Kanbus project with default configuration
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus move kanbus-test01 does-not-exist"
    Then the command should fail with exit code 1
    And stderr should contain "unknown issue type"
    And issue "kanbus-test01" should have type "task"

  Scenario: Move enforces hierarchy constraints
    Given a Kanbus project with default configuration
    And an issue "kanbus-epic01" of type "epic" with status "open"
    And an issue "kanbus-child01" of type "task" with status "open" and parent "kanbus-epic01"
    When I run "kanbus move kanbus-child01 initiative"
    Then the command should fail with exit code 1
    And stderr should contain "invalid parent-child relationship"
    And issue "kanbus-child01" should have type "task"

  Scenario: Move is blocked by epic entry guardrail policy
    Given a Kanbus project with default configuration
    And a policy file "epic-entry.policy" with content:
      """
      Feature: Epic entry guardrails

        Rule: Active-state bypass prevention
          Scenario: Epic in in_progress must have children
            Given the issue type is "epic"
            Given the issue status is "in_progress"
            When updating an issue
            Then the issue must have at least 1 child issues
      """
    And an issue "kanbus-test01" of type "task" with status "in_progress"
    When I run "kanbus move kanbus-test01 epic"
    Then the command should fail with exit code 1
    And stderr should contain "policy violation"
    And stderr should contain "issue has 0 child issue(s) but must have at least 1"
    And issue "kanbus-test01" should have type "task"
