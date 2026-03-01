Feature: Policy CLI commands
  As a project manager
  I want dedicated CLI commands for policy discovery and validation
  So that I can inspect and verify policy behavior directly

  Scenario: Policy list shows loaded files and scenarios
    Given a Kanbus project with default configuration
    And a policy file "sample.policy" with content:
      """
      Feature: Sample policy

        Scenario: Require assignee
          Then the issue must have field "assignee"
      """
    When I run "kanbus policy list"
    Then the command should succeed
    And stdout should contain "sample.policy"
    And stdout should contain "Feature: Sample policy"
    And stdout should contain "Scenario: Require assignee"

  Scenario: Policy validate passes for valid syntax
    Given a Kanbus project with default configuration
    And a policy file "valid.policy" with content:
      """
      Feature: Valid policy

        Scenario: Validate syntax
          Given the issue type is "task"
          Then the field "status" must be "open"
      """
    When I run "kanbus policy validate"
    Then the command should succeed
    And stdout should contain "All 1 policy files are valid"

  Scenario: Policy validate fails for invalid syntax
    Given a Kanbus project with default configuration
    And a policy file "invalid.policy" with content:
      """
      Scenario: Missing feature header
        Given the issue type is "task"
      """
    When I run "kanbus policy validate"
    Then the command should fail with exit code 1
    And stderr should not contain "Traceback"
    And stderr should contain "failed to parse"

  Scenario: Policy check passes when no violations are found
    Given a Kanbus project with default configuration
    And a policy file "status-open.policy" with content:
      """
      Feature: Status policy

        Scenario: Status must remain open
          Given the issue type is "task"
          Then the field "status" must be "open"
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus policy check kanbus-test01"
    Then the command should succeed
    And stdout should contain "All policies passed for kanbus-test01"

  Scenario: Policy check reports violations
    Given a Kanbus project with default configuration
    And a policy file "require-assignee.policy" with content:
      """
      Feature: Assignee policy

        Scenario: Assignee required
          Given the issue type is "task"
          Then the issue must have field "assignee"
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus policy check kanbus-test01"
    Then the command should fail with exit code 1
    And stderr should not contain "Traceback"
    And stderr should contain "Found 1 policy violation(s)"
    And stderr should contain "require-assignee.policy"
