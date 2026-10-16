Feature: LLM usage cost report
  As a Kanbus user
  I want the cost report to show every token and say which calls have no known price
  So that real LLM spend is never reported as zero

  Background:
    Given a Kanbus project with default configuration

  Scenario: Cost report without a usage log
    When I run "kanbus cost"
    Then the command should succeed
    And stdout should contain "No LLM usage logs found."

  Scenario: Cost report totals tokens and counts unpriced calls
    Given the LLM usage log contains entries:
      | operation                   | total_tokens | cost   | age_days |
      | right_now_summary           | 100          | none   | 0        |
      | right_now_summary           | 40           | none   | 0        |
      | compaction_activity_summary | 50           | 0.0025 | 0        |
    When I run "kanbus cost"
    Then the command should succeed
    And stdout should contain "Total Tokens:   190"
    And stdout should contain "Total Cost:     $0.0025"
    And stdout should contain "Unpriced Calls: 2"

  Scenario: Cost report limits entries to recent days
    Given the LLM usage log contains entries:
      | operation         | total_tokens | cost   | age_days |
      | right_now_summary | 100          | none   | 0        |
      | right_now_summary | 70           | 0.0100 | 10       |
    When I run "kanbus cost --days 5"
    Then the command should succeed
    And stdout should contain "Total Tokens:   100"
    And stdout should contain "Total Cost:     $0.0000"
    And stdout should contain "Unpriced Calls: 1"
