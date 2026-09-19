@console @kbs80
Feature: Console issue write controls
  As a Kanbus user
  I want to comment on issues and use allowed status transitions
  So that validated writes remain visible and recoverable

  Scenario: Comment and status APIs validate writes and return refreshed issues
    Given the console is open
    And the console has only these issues:
      | id             | title          | status |
      | kbs-write-open | Write controls | open   |
    When I add a comment through the issue write API for "kbs-write-open" with text "A normal reply"
    Then the issue write API response should be successful with comment "A normal reply"
    When I change status through the issue write API for "kbs-write-open" to "closed"
    Then the issue write API response should be successful with status "closed"
    When I change status through the issue write API for "kbs-write-open" to "not-a-status"
    Then the issue write API response should fail with status 400 and error containing "status"

  Scenario: A reply to a blocked agent resumes the package
    Given the console is open
    And the console has only these issues:
      | id              | title           | status  |
      | kbs-write-block | Awaiting reply | blocked |
    And the issue "kbs-write-block" has a blocked router conversation
    When I add a comment through the issue write API for "kbs-write-block" with text "Please continue"
    Then the issue write API response should be successful with comment "Please continue"
    And the issue write API response should report the agent was resumed
    And the issue write API response should include status "in_progress"

  Scenario: Detail panel exposes only allowed transitions and reports a successful write
    Given the console is open
    And the console has only these issues:
      | id            | title          | status |
      | kbs-write-ui  | Write controls | open   |
    When I switch to the "Tasks" tab
    And I open the task "Write controls"
    Then the issue write controls should show allowed statuses "open,in_progress,closed,backlog"
    When I enter comment "Visible from the composer" in the issue composer
    And the issue comment write is delayed
    And I submit the issue comment
    Then the issue write controls should show a pending state
    When the mocked issue comment write succeeds
    Then the issue write controls should show a success state

  Scenario: Detail panel reports a failed comment write
    Given the console is open
    And the console has only these issues:
      | id             | title          | status |
      | kbs-write-error | Write failure | open   |
    When I switch to the "Tasks" tab
    And I open the task "Write failure"
    And the issue comment write is mocked to fail with "write rejected"
    When I enter comment "This should fail" in the issue composer
    And I submit the issue comment
    Then the issue write controls should show an error containing "write rejected"
