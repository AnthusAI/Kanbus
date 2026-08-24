Feature: Issue Compaction
  As a developer
  I want to summarize noisy, complex issues using an LLM
  So that I can load them faster and get a concise overview without reading the full history

  Background:
    Given a Kanbus project with default configuration
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"
    And mock AI is enabled

  @console-server
  Scenario: Running the summarize subcommand for an active issue
    Given an issue "kanbus-compaction01" exists with title "Complex issue to summarize"
    And the issue "kanbus-compaction01" has status "in_progress"
    And the issue "kanbus-compaction01" has a comment with text "We need to rethink the database."
    And the issue "kanbus-compaction01" has a comment with text "Let's use PostgreSQL instead of JSON."
    When I run "kanbus summarize kanbus-compaction01"
    Then the command should succeed
    And the issue "kanbus-compaction01" should have a summary comment
    And the summary comment for issue "kanbus-compaction01" should contain "Activity Summary"
    And the summary comment for issue "kanbus-compaction01" should contain "Rewritten Description"

  @console-server
  Scenario: Running the summarize subcommand for an archived issue
    Given an issue "kanbus-compaction02" exists with title "Old completed issue"
    And the issue "kanbus-compaction02" has status "closed"
    And the issue "kanbus-compaction02" was updated 60 days ago
    And the issue "kanbus-compaction02" has a comment with text "Fixed in v1.2.3."
    When I run "kanbus summarize kanbus-compaction02"
    Then the command should succeed
    And the issue "kanbus-compaction02" should have a summary comment
    And the summary comment for issue "kanbus-compaction02" should contain "Activity Summary"
    And the summary comment for issue "kanbus-compaction02" should contain "Rewritten Description"

  @console-server
  Scenario: Structured logging of LLM usage and costs
    Given an issue "kanbus-compaction03" exists with title "Another complex issue"
    When I run "kanbus summarize kanbus-compaction03"
    Then the command should succeed
    And the system records a structured log entry for the LLM usage

  @console-server
  Scenario: Querying an issue uses the virtualized summary view
    Given an issue "kanbus-compaction04" exists with title "Issue to show"
    And the issue "kanbus-compaction04" has a summary comment containing:
      """
      ### Rewritten Description
      Virtualized summary text.

      ### Activity Summary
      Summary activity details.
      """
    When I run "kanbus show kanbus-compaction04"
    Then the command should succeed
    And stdout should contain "Virtualized summary text"
    And stdout should contain "Summary activity details"
