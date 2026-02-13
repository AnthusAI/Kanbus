Feature: Issue list formatting
  The list output should present key fields agents need while remaining token-efficient.

  Scenario: List shows parent in porcelain mode
    Given a Taskulus project with default configuration
    And an issue "tsk-parent" exists
    And an issue "tsk-child" exists with status "open"
    And issue "tsk-child" has parent "tsk-parent"
    When I run "tsk list --porcelain"
    Then stdout should contain the line "T | tsk-child | tsk-parent | open | P2 | Title"
