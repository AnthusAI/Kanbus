Feature: Issue display

  Scenario: Show issue details
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists with title "Implement OAuth2 flow"
    And issue "tsk-aaa" has status "open" and type "task"
    When I run "tsk show tsk-aaa"
    Then the command should succeed
    And stdout should contain "Implement OAuth2 flow"
    And stdout should contain "open"
    And stdout should contain "task"

  Scenario: Show issue as JSON
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists with title "Implement OAuth2 flow"
    When I run "tsk show tsk-aaa --json"
    Then the command should succeed
    And stdout should contain "\"id\": \"tsk-aaa\""
    And stdout should contain "\"title\": \"Implement OAuth2 flow\""

  Scenario: Show missing issue
    Given a Taskulus project with default configuration
    When I run "tsk show tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Show issue description
    Given a Taskulus project with default configuration
    And an issue "tsk-desc" exists with title "Describe me"
    And issue "tsk-desc" has description "Detailed description"
    When I run "tsk show tsk-desc"
    Then the command should succeed
    And stdout should contain "Description:"
    And stdout should contain "Detailed description"

  Scenario: Show issue labels
    Given a Taskulus project with default configuration
    And an issue "tsk-labels" exists
    And issue "tsk-labels" has labels "auth, urgent"
    When I run "tsk show tsk-labels"
    Then the command should succeed
    And stdout should contain "Labels: auth, urgent"

  Scenario: Format issue display includes labels
    Given a Taskulus project with default configuration
    And an issue "tsk-labels" exists
    And issue "tsk-labels" has labels "auth, urgent"
    When I format issue "tsk-labels" for display
    Then the formatted output should contain text "Labels: auth, urgent"

  Scenario: Format issue display applies color when enabled
    Given a Taskulus project with default configuration
    And an issue "tsk-aaa" exists with title "Implement OAuth2 flow"
    When I format issue "tsk-aaa" for display with color enabled
    Then the formatted output should contain ANSI color codes

  Scenario Outline: Format issue display applies colors for status, priority, and type
    Given a Taskulus project with default configuration
    And an issue "<identifier>" exists with status "<status>", priority <priority>, type "<issue_type>", and assignee "<assignee>"
    When I format issue "<identifier>" for display with color enabled
    Then the formatted output should contain ANSI color codes
    And the formatted output should contain text "<status>"
    And the formatted output should contain text "<issue_type>"

    Examples:
      | identifier  | status       | priority | issue_type | assignee         |
      | tsk-color1  | in_progress  | 0        | chore      | dev@example.com  |
      | tsk-color2  | blocked      | 3        | event      | dev@example.com  |
      | tsk-color3  | closed       | 4        | task       | dev@example.com  |
      | tsk-color4  | deferred     | 9        | unknown    | dev@example.com  |
      | tsk-color5  | unknown      | 2        | task       | dev@example.com  |

  Scenario: Format issue display uses configured status colors
    Given a Taskulus repository with a .taskulus.yml file containing a bright white status color
    And issue "tsk-bright" has title "Bright status"
    When I format issue "tsk-bright" for display with color enabled
    Then the formatted output should contain ANSI color codes

  Scenario Outline: Format issue display uses fallback priority colors without configuration
    Given a Taskulus project with default configuration
    And an issue "tsk-fallback" exists with status "open"
    And issue "tsk-fallback" has priority <priority>
    When I format issue "tsk-fallback" for display with color enabled without configuration
    Then the formatted output should contain ANSI color codes

    Examples:
      | priority |
      | 0        |
      | 3        |
      | 4        |
