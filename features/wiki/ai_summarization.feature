Feature: AI summarization in wiki templates
  As a Kanbus user
  I want to use an AI summarize function in my wiki templates
  So that I can automatically generate issue summaries

  Scenario: Wiki template uses summarize function
    Given a Kanbus project with AI configured
    And an issue "kanbus-1" exists
    And a wiki page "report.md" with content:
      """
      {{ ai_summarize(issue("kanbus-1")) }}
      """
    When I run "kanbus wiki render project/wiki/report.md"
    Then the command should succeed
    And the rendered wiki should contain a generated summary for "kanbus-1"
