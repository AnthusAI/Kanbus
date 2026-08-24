Feature: Issue Lifecycle Management System
  As a system utility
  I want a lifecycle subcommand for issues
  So that I can continuously compact history and manage old issues in bulk

  Background:
    Given a Kanbus project with default configuration
    And the AI provider is configured as "litellm"
    And mock AI is enabled

  Scenario: Dry-run batch compaction (shows what would be compacted)
    Given an issue "tskl-1" of type "bug" in status "closed"
    And issue "tskl-1" was updated 40 days ago
    And issue "tskl-1" has 3 comments
    When I run "kanbus lifecycle compact --archived-only --dry-run"
    Then the command should succeed
    And stdout should contain "Dry-run mode: no issues were modified"
    And stdout should contain "Would summarize tskl-1"

  Scenario: Batch compact all eligible archived issues
    Given an issue "tskl-2" of type "task" in status "done"
    And issue "tskl-2" was updated 35 days ago
    And issue "tskl-2" has 5 comments
    Given an issue "tskl-3" of type "epic" in status "in_progress"
    And issue "tskl-3" was updated 2 days ago
    And issue "tskl-3" has 2 comments
    When I run "kanbus lifecycle compact --archived-only"
    Then the command should succeed
    And stdout should contain "Summary saved for tskl-2"
    And stdout should not contain "Summary saved for tskl-3"
    And stdout should contain "Total cost:"

  Scenario: Respecting the --max-items limit
    Given an issue "tskl-4" of type "bug" in status "closed"
    And issue "tskl-4" was updated 40 days ago
    Given an issue "tskl-5" of type "bug" in status "closed"
    And issue "tskl-5" was updated 40 days ago
    When I run "kanbus lifecycle compact --archived-only --max-items 1"
    Then the command should succeed
    And stdout should contain "Summary saved for"
    And stdout should contain "Processed 1 issues"

  Scenario: Skipping issues that are already summarized
    Given an issue "tskl-6" of type "task" in status "closed"
    And issue "tskl-6" was updated 40 days ago
    And issue "tskl-6" has a summary comment
    When I run "kanbus lifecycle compact --archived-only"
    Then the command should succeed
    And stdout should not contain "Summary saved for tskl-6"

  Scenario: Recursive backfill during compaction
    Given an issue "tskl-parent" of type "epic" in status "closed"
    And issue "tskl-parent" was updated 40 days ago
    Given an issue "tskl-child" of type "task" in status "in_progress"
    And issue "tskl-child" has parent "tskl-parent"
    And issue "tskl-child" was updated 2 days ago
    And issue "tskl-child" has 2 comments
    When I run "kanbus lifecycle compact --archived-only"
    Then the command should succeed
    And stdout should contain "Summary saved for tskl-child"
    And stdout should contain "Summary saved for tskl-parent"
