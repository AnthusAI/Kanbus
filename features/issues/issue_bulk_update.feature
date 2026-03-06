Feature: Issue bulk update

  Scenario: Update issues selected by filters
    Given a Kanbus project with default configuration
    And an issue "kanbus-task-open" exists with status "open", priority 2, type "task", and assignee "sam"
    And an issue "kanbus-task-done" exists with status "done", priority 2, type "task", and assignee "sam"
    And an issue "kanbus-bug-open" exists with status "open", priority 2, type "bug", and assignee "sam"
    When I run "kanbus bulk update --where-type task --where-status open --set-status in_progress --set-assignee alex"
    Then the command should succeed
    And issue "kanbus-task-open" should have status "in_progress"
    And issue "kanbus-task-open" should have assignee "alex"
    And issue "kanbus-task-done" should have status "done"
    And issue "kanbus-task-done" should have assignee "sam"
    And issue "kanbus-bug-open" should have status "open"
    And issue "kanbus-bug-open" should have assignee "sam"

  Scenario: Update issues selected by explicit IDs
    Given a Kanbus project with default configuration
    And an issue "kanbus-id-one" exists with status "open", priority 2, type "task", and assignee "sam"
    And an issue "kanbus-id-two" exists with status "open", priority 2, type "bug", and assignee "sam"
    And an issue "kanbus-id-three" exists with status "open", priority 2, type "story", and assignee "sam"
    When I run "kanbus bulk update --id kanbus-id-one --id kanbus-id-two --set-status closed"
    Then the command should succeed
    And issue "kanbus-id-one" should have status "closed"
    And issue "kanbus-id-two" should have status "closed"
    And issue "kanbus-id-three" should have status "open"

  Scenario: Bulk update prints a summary of changes
    Given a Kanbus project with default configuration
    And an issue "kanbus-sum-one" exists with status "open", priority 2, type "task", and assignee "sam"
    And an issue "kanbus-sum-two" exists with status "open", priority 2, type "task", and assignee "sam"
    And an issue "kanbus-sum-three" exists with status "done", priority 2, type "task", and assignee "sam"
    When I run "kanbus bulk update --where-status open --set-status in_progress"
    Then the command should succeed
    And stdout should contain "Updated 2 issue(s)"
