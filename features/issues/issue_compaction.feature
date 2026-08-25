Feature: Issue Compaction
  As a developer
  I want to summarize noisy, complex issues using an LLM
  So that I can load them faster and get a concise overview without reading the full history

  Background:
    Given a Kanbus project with default configuration
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"
    And mock AI is enabled

  Scenario: Summarize DATAP-602 style epic into description and activity summary
    Given an issue "DATAP-602" exists with title "Behavior specifications using ground-truth evaluation repositories"
    And issue "DATAP-602" has description "I'm going to add a set of Gherkin-based BDD specifications aimed at evaluating the scanner end-to-end. As an example:\nGiven this repository that we found on GitHub that we know tracks SSNs,\nWhen I run the scanner,\nThen I should end up with a SSN data item in the dataflow.json file."
    And the issue "DATAP-602" has a comment with text "## Progress Summary\n\nEpic status: in progress (1 of 6 child tasks complete)."
    When I run "kanbus summarize DATAP-602"
    Then the command should succeed
    And issue "DATAP-602" description should equal "I'm going to add a set of Gherkin-based BDD specifications aimed at evaluating the scanner end-to-end. As an example:\nGiven this repository that we found on GitHub that we know tracks SSNs,\nWhen I run the scanner,\nThen I should end up with a SSN data item in the dataflow.json file."
    And the issue "DATAP-602" should have a summary comment
    And the summary comment for issue "DATAP-602" should have rewritten description "Mock rewritten description for DATAP-602."
    And the summary rewritten description for issue "DATAP-602" should be shorter than the original description
    And the summary comment for issue "DATAP-602" should contain "Mock activity summary for DATAP-602."
    When I run "kanbus show DATAP-602"
    Then the command should succeed
    And stdout should contain "Mock rewritten description for DATAP-602."
    And stdout should contain "Mock activity summary for DATAP-602."
    And stdout should not contain "## Progress Summary"
    When I run "kanbus show DATAP-602 --raw"
    Then the command should succeed
    And stdout should contain "I'm going to add a set of Gherkin-based BDD specifications"
    And stdout should contain "## Progress Summary"

  @console-server
  Scenario: Running the summarize subcommand for an active issue
    Given an issue "kanbus-compaction01" exists with title "Complex issue to summarize"
    And the issue "kanbus-compaction01" has status "in_progress"
    And the issue "kanbus-compaction01" has a comment with text "We need to rethink the database."
    And the issue "kanbus-compaction01" has a comment with text "Let's use PostgreSQL instead of JSON."
    When I run "kanbus summarize kanbus-compaction01"
    Then the command should succeed
    And the issue "kanbus-compaction01" should have a summary comment
    And the summary comment for issue "kanbus-compaction01" should have rewritten description "Mock rewritten description for kanbus-compaction01."
    And the summary comment for issue "kanbus-compaction01" should contain "Mock activity summary for kanbus-compaction01."

  @console-server
  Scenario: Running the summarize subcommand for an archived issue
    Given an issue "kanbus-compaction02" exists with title "Old completed issue"
    And the issue "kanbus-compaction02" has status "closed"
    And the issue "kanbus-compaction02" was updated 60 days ago
    And the issue "kanbus-compaction02" has a comment with text "Fixed in v1.2.3."
    When I run "kanbus summarize kanbus-compaction02"
    Then the command should succeed
    And the issue "kanbus-compaction02" should have a summary comment
    And the summary comment for issue "kanbus-compaction02" should have rewritten description "Mock rewritten description for kanbus-compaction02."
    And the summary comment for issue "kanbus-compaction02" should contain "Mock activity summary for kanbus-compaction02."

  @console-server
  Scenario: Structured logging of LLM usage and costs
    Given an issue "kanbus-compaction03" exists with title "Another complex issue"
    When I run "kanbus summarize kanbus-compaction03"
    Then the command should succeed
    And the system records a structured log entry for the LLM usage
