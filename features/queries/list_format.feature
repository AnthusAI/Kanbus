Feature: Issue list formatting
  The list output should present key fields agents need while remaining token-efficient.

  Scenario: List shows parent in porcelain mode
    Given a Kanbus project with default configuration
    And an issue "kanbus-parent" exists
    And an issue "kanbus-child" exists with status "open"
    And issue "kanbus-child" has parent "kanbus-parent"
    When I run "kanbus list --porcelain"
    Then stdout should contain the line "T | child | parent | open | P2 | Title"

  Scenario: List formatting applies default colors
    Given a Kanbus project with default configuration
    And issues for list color coverage exist
    When I format list lines for color coverage
    Then each formatted line should contain ANSI color codes

  Scenario: List formatting uses configured bright white status colors
    Given a Kanbus repository with a .kanbus.yml file containing a bright white status color
    And issues for list color coverage exist
    When I format list lines for color coverage
    Then each formatted line should contain ANSI color codes

  Scenario: List formatting ignores invalid status colors
    Given a Kanbus repository with a .kanbus.yml file containing an invalid status color
    And an issue "kanbus-colorless" exists with status "open"
    When I format the list line for issue "kanbus-colorless"
    Then the formatted output should contain text "open"

  Scenario: List formatting respects NO_COLOR
    Given a Kanbus project with default configuration
    And an issue "kanbus-colorless" exists with status "open"
    When I format the list line for issue "kanbus-colorless" with NO_COLOR set
    Then the formatted output should contain no ANSI color codes
