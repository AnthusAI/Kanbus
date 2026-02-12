Feature: Workflow status transitions
  As a project manager
  I want status transitions to follow defined workflows
  So that issues move through a predictable lifecycle

  Scenario Outline: Valid transitions in default workflow
    Given a Taskulus project with default configuration
    And an issue "tsk-test01" of type "task" with status "<from_status>"
    When I run "tsk update tsk-test01 --status <to_status>"
    Then the command should succeed
    And issue "tsk-test01" should have status "<to_status>"

    Examples:
      | from_status | to_status   |
      | open        | in_progress |
      | open        | closed      |
      | open        | deferred    |
      | in_progress | open        |
      | in_progress | blocked     |
      | in_progress | closed      |
      | blocked     | in_progress |
      | blocked     | closed      |
      | closed      | open        |
      | deferred    | open        |
      | deferred    | closed      |

  Scenario Outline: Invalid transitions in default workflow
    Given a Taskulus project with default configuration
    And an issue "tsk-test01" of type "task" with status "<from_status>"
    When I run "tsk update tsk-test01 --status <to_status>"
    Then the command should fail with exit code 1
    And stderr should contain "invalid transition"
    And issue "tsk-test01" should have status "<from_status>"

    Examples:
      | from_status | to_status   |
      | open        | blocked     |
      | blocked     | open        |
      | blocked     | deferred    |
      | closed      | in_progress |
      | closed      | blocked     |
      | closed      | deferred    |
      | deferred    | in_progress |
      | deferred    | blocked     |

  Scenario: Type-specific workflow overrides default
    Given a Taskulus project with default configuration
    And an issue "tsk-epic01" of type "epic" with status "open"
    When I run "tsk update tsk-epic01 --status deferred"
    Then the command should fail with exit code 1
    And stderr should contain "invalid transition"
