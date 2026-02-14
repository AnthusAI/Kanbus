Feature: Issue display

  Scenario: Show issue details
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Implement OAuth2 flow"
    And issue "kanbus-aaa" has status "open" and type "task"
    When I run "kanbus show kanbus-aaa"
    Then the command should succeed
    And stdout should contain "Implement OAuth2 flow"
    And stdout should contain "open"
    And stdout should contain "task"

  Scenario: Show issue as JSON
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Implement OAuth2 flow"
    When I run "kanbus show kanbus-aaa --json"
    Then the command should succeed
    And stdout should contain "\"id\": \"kanbus-aaa\""
    And stdout should contain "\"title\": \"Implement OAuth2 flow\""

  Scenario: Show missing issue
    Given a Kanbus project with default configuration
    When I run "kanbus show kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Show issue description
    Given a Kanbus project with default configuration
    And an issue "kanbus-desc" exists with title "Describe me"
    And issue "kanbus-desc" has description "Detailed description"
    When I run "kanbus show kanbus-desc"
    Then the command should succeed
    And stdout should contain "Description:"
    And stdout should contain "Detailed description"

  Scenario: Show issue labels
    Given a Kanbus project with default configuration
    And an issue "kanbus-labels" exists
    And issue "kanbus-labels" has labels "auth, urgent"
    When I run "kanbus show kanbus-labels"
    Then the command should succeed
    And stdout should contain "Labels: auth, urgent"

  Scenario: Format issue display includes labels
    Given a Kanbus project with default configuration
    And an issue "kanbus-labels" exists
    And issue "kanbus-labels" has labels "auth, urgent"
    When I format issue "kanbus-labels" for display
    Then the formatted output should contain text "Labels: auth, urgent"

  Scenario: Format issue display applies color when enabled
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Implement OAuth2 flow"
    When I format issue "kanbus-aaa" for display with color enabled
    Then the formatted output should contain ANSI color codes

  Scenario Outline: Format issue display applies colors for status, priority, and type
    Given a Kanbus project with default configuration
    And an issue "<identifier>" exists with status "<status>", priority <priority>, type "<issue_type>", and assignee "<assignee>"
    When I format issue "<identifier>" for display with color enabled
    Then the formatted output should contain ANSI color codes
    And the formatted output should contain text "<status>"
    And the formatted output should contain text "<issue_type>"

    Examples:
      | identifier  | status       | priority | issue_type | assignee         |
      | kanbus-color1  | in_progress  | 0        | chore      | dev@example.com  |
      | kanbus-color2  | blocked      | 3        | event      | dev@example.com  |
      | kanbus-color3  | closed       | 4        | task       | dev@example.com  |
      | kanbus-color4  | deferred     | 9        | unknown    | dev@example.com  |
      | kanbus-color5  | unknown      | 2        | task       | dev@example.com  |

  Scenario: Format issue display uses configured status colors
    Given a Kanbus repository with a .kanbus.yml file containing a bright white status color
    And issue "kanbus-bright" has title "Bright status"
    When I format issue "kanbus-bright" for display with color enabled
    Then the formatted output should contain ANSI color codes

  Scenario Outline: Format issue display uses fallback priority colors without configuration
    Given a Kanbus project with default configuration
    And an issue "kanbus-fallback" exists with status "open"
    And issue "kanbus-fallback" has priority <priority>
    When I format issue "kanbus-fallback" for display with color enabled without configuration
    Then the formatted output should contain ANSI color codes

    Examples:
      | priority |
      | 0        |
      | 3        |
      | 4        |
