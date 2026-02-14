@console
Feature: Console comment timestamps
  As a Kanbus user
  I want comment timestamps to use the configured time zone
  So that updates are easy to read

  Scenario: Comments display in UTC by default
    Given the console is open
    And the console has a comment from "Sam" at "2026-02-13T23:13:00.000Z" on task "Add structured logging"
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then the comment timestamp should be "Friday, February 13, 2026 11:13 PM UTC"

  Scenario: Comments display in the configured time zone
    Given the console is open
    And the console configuration sets time zone "America/Los_Angeles"
    And the console has a comment from "Sam" at "2026-02-13T23:13:00.000Z" on task "Add structured logging"
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then the comment timestamp should be "Friday, February 13, 2026 3:13 PM PST"
