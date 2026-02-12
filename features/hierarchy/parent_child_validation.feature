Feature: Parent-child hierarchy validation

  Scenario Outline: Valid parent-child relationships
    Given a Taskulus project with default configuration
    And a "<parent_type>" issue "tsk-parent" exists
    When I run "tsk create Child Task --type <child_type> --parent tsk-parent"
    Then the command should succeed

    Examples:
      | parent_type | child_type |
      | initiative  | epic       |
      | epic        | task       |
      | task        | sub-task   |
      | epic        | bug        |
      | task        | story      |

  Scenario Outline: Invalid parent-child relationships
    Given a Taskulus project with default configuration
    And a "<parent_type>" issue "tsk-parent" exists
    When I run "tsk create Child Task --type <child_type> --parent tsk-parent"
    Then the command should fail with exit code 1
    And stderr should contain "invalid parent-child"

    Examples:
      | parent_type | child_type  |
      | epic        | initiative  |
      | task        | epic        |
      | sub-task    | task        |
      | bug         | task        |
      | story       | sub-task    |

  Scenario: Standalone issues do not require a parent
    Given a Taskulus project with default configuration
    When I run "tsk create Standalone Task --type task"
    Then the command should succeed
    And the created issue should have no parent

  Scenario: Non-hierarchical types cannot have children
    Given a Taskulus project with default configuration
    And a "bug" issue "tsk-bug01" exists
    When I run "tsk create Child --type task --parent tsk-bug01"
    Then the command should fail with exit code 1
