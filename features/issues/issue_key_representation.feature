Feature: Issue key representation
  As a Taskulus user
  I want a consistent way to display issue identifiers
  So that global and project contexts show the expected form

  Scenario Outline: Format issue key for display
    Given an issue identifier "<identifier>"
    And the display context is "<context>"
    When I format the issue key
    Then the formatted key should be "<expected>"

    Examples:
      | identifier                                   | context  | expected        |
      | tsk-0123456789ab                             | global   | tsk-012345      |
      | tsk-0123456789ab                             | project  | 012345          |
      | 42                                           | global   | 42              |
      | 42                                           | project  | 42              |
      | tsk-123e4567-e89b-12d3-a456-426614174000     | global   | tsk-123e45      |
      | tsk-123e4567-e89b-12d3-a456-426614174000     | project  | 123e45          |
      | tsk-abc123.7                                | global   | tsk-abc123.7    |
      | tsk-abc123.7                                | project  | abc123.7        |
      | customid                                    | global   | custom          |
      | -abc123                                     | global   | abc123          |
      | abc123.7                                    | global   | abc123.7        |
