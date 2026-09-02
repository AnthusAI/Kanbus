Feature: Right now issue fields
  As a Kanbus maintainer
  I want issues to store right-now summary metadata
  So that summaries can be displayed and updated consistently

  Scenario: Issue with right now fields round-trips through load and save
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Implement OAuth2 flow"
    And issue "kanbus-aaa" has right now summary "Waiting on API credentials"
    And issue "kanbus-aaa" has right now updated at "2026-02-11T12:00:00Z"
    When issue "kanbus-aaa" is saved and reloaded from disk
    Then issue "kanbus-aaa" should have right now summary "Waiting on API credentials"
    And issue "kanbus-aaa" should have right now updated at "2026-02-11T12:00:00Z"

  Scenario: Issue without right now fields loads with null values
    Given a Kanbus project with default configuration
    And an issue "kanbus-bbb" exists with title "Write tests"
    When issue "kanbus-bbb" is loaded from disk
    Then issue "kanbus-bbb" should have no right now summary
    And issue "kanbus-bbb" should have no right now updated at

  Scenario: get_right_now_summary returns the summary when present
    Given a Kanbus project with default configuration
    And an issue "kanbus-ccc" exists with title "Review PR"
    And issue "kanbus-ccc" has right now summary "Blocked on review"
    When I read the right now summary for issue "kanbus-ccc"
    Then the right now summary result should be "Blocked on review"

  Scenario: get_right_now_summary returns none when absent
    Given a Kanbus project with default configuration
    And an issue "kanbus-ddd" exists with title "Deploy release"
    When I read the right now summary for issue "kanbus-ddd"
    Then the right now summary result should be unset
