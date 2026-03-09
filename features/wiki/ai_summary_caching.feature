Feature: AI summary caching
  As a Kanbus user
  I want AI summaries to be cached based on issue content
  So that rendering wiki pages is fast and cheap

  Scenario: Summarize function uses cache on second render
    Given a Kanbus project with AI configured
    And an issue "kanbus-1" exists
    And a wiki page "report.md" with content:
      """
      {{ ai_summarize(issue("kanbus-1")) }}
      """
    When I run "kanbus wiki render project/wiki/report.md"
    Then the AI provider API should be called
    When I run "kanbus wiki render project/wiki/report.md"
    Then the AI provider API should not be called
