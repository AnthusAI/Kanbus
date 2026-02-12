Feature: In-memory index building

  Scenario: Index builds lookup maps from issue files
    Given a Taskulus project with 5 issues of varying types and statuses
    When the index is built
    Then the index should contain 5 issues
    And querying by status "open" should return the correct issues
    And querying by type "task" should return the correct issues
    And querying by parent should return the correct children

  Scenario: Index computes reverse dependency links
    Given a Taskulus project with default configuration
    And issue "tsk-aaa" exists with a blocked-by dependency on "tsk-bbb"
    When the index is built
    Then the reverse dependency index should show "tsk-bbb" blocks "tsk-aaa"
