@console
Feature: Console issue detail metadata
  As a Kanbus user
  I want issue timestamps and assignee shown in the detail view
  So that I can see recent activity quickly

  Scenario: Detail view shows created timestamp and assignee
    Given the console is open
    And the console has a task "Add structured logging" created at "2026-02-13T23:13:00.000Z" updated at "2026-02-13T23:13:00.000Z"
    And the console has an assignee "Ryan Porter" on task "Add structured logging"
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then the issue metadata should include created timestamp "Friday, February 13, 2026 11:13 PM UTC"
    And the issue metadata should include assignee "Ryan Porter"

  Scenario: Detail view shows updated timestamp when it differs
    Given the console is open
    And the console has a task "Add structured logging" created at "2026-02-13T23:13:00.000Z" updated at "2026-02-14T01:13:00.000Z"
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then the issue metadata should include updated timestamp "Saturday, February 14, 2026 1:13 AM UTC"

  Scenario: Detail view shows closed timestamp when present
    Given the console is open
    And the console has a closed task "Add structured logging" created at "2026-02-13T23:13:00.000Z" updated at "2026-02-14T01:13:00.000Z" closed at "2026-02-14T02:13:00.000Z"
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then the issue metadata should include closed timestamp "Saturday, February 14, 2026 2:13 AM UTC"
