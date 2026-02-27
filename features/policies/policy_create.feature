Feature: Policy evaluation on issue creation
  As a project manager
  I want policies to be evaluated when creating issues
  So that new issues meet project standards from the start

  Scenario: Policy passes and issue is created
    Given a Kanbus project with default configuration
    And a policy file "require-description.policy" with content:
      """
      Feature: Require description

        Scenario: All issues need description
          When creating an issue
          Then the description must not be empty
      """
    When I run "kanbus create \"Test Issue\" --description \"This is a test\""
    Then the command should succeed
    And stdout should contain "kanbus-"

  Scenario: Policy fails and issue is not created
    Given a Kanbus project with default configuration
    And a policy file "require-description.policy" with content:
      """
      Feature: Require description

        Scenario: All issues need description
          When creating an issue
          Then the description must not be empty
      """
    When I run "kanbus create \"Test Issue\""
    Then the command should fail with exit code 1
    And stderr should contain "policy violation"
    And stderr should contain "description is empty"

  Scenario: Type-specific policy on creation
    Given a Kanbus project with default configuration
    And a policy file "bug-prefix.policy" with content:
      """
      Feature: Bug naming convention

        Scenario: Bugs must have BUG prefix
          Given the issue type is "bug"
          When creating an issue
          Then the title must match pattern "^BUG-"
      """
    When I run "kanbus create \"Fix login\" --type bug"
    Then the command should fail with exit code 1
    And stderr should contain "does not match pattern"

  Scenario: Policy passes for different type
    Given a Kanbus project with default configuration
    And a policy file "bug-prefix.policy" with content:
      """
      Feature: Bug naming convention

        Scenario: Bugs must have BUG prefix
          Given the issue type is "bug"
          When creating an issue
          Then the title must match pattern "^BUG-"
      """
    When I run "kanbus create \"Implement feature\" --type task"
    Then the command should succeed
