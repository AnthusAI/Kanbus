Feature: Issue key representation
  As a Kanbus user
  I want a consistent way to display issue identifiers
  So that global and project contexts show the expected form

  Scenario Outline: Format issue key for display
    Given an issue identifier "<identifier>"
    And the display context is "<context>"
    When I format the issue key
    Then the formatted key should be "<expected>"

    Examples:
      | identifier                                   | context  | expected        |
      | kanbus-0123456789ab                             | global   | kanbus-012345      |
      | kanbus-0123456789ab                             | project  | 012345          |
      | 42                                           | global   | 42              |
      | 42                                           | project  | 42              |
      | kanbus-123e4567-e89b-12d3-a456-426614174000     | global   | kanbus-123e45      |
      | kanbus-123e4567-e89b-12d3-a456-426614174000     | project  | 123e45          |
      | kanbus-abc123.7                                | global   | kanbus-abc123.7    |
      | kanbus-abc123.7                                | project  | abc123.7        |
      | customid                                    | global   | custom          |
      | -abc123                                     | global   | abc123          |
      | abc123.7                                    | global   | abc123.7        |
