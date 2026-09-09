Feature: Right now just-in-time backfill
  As a Kanbus user
  I want missing right-now summaries generated when I look at Now
  So that the feed backfills recursively instead of staying on placeholders

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Now backfills a missing summary
    Given an issue "kanbus-jit1" exists with title "Needs a summary"
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should contain "Mock right-now summary for kanbus-jit1."
    And issue "kanbus-jit1" should have a mock right now summary

  Scenario: Now backfills children before the parent
    Given an issue "kanbus-jit-epic" of type "epic" with status "open" and title "Parent epic"
    And an issue "kanbus-jit-task" of type "task" with status "open" and parent "kanbus-jit-epic"
    When I run "kanbus now kanbus-jit-epic"
    Then the command should succeed
    And issue "kanbus-jit-task" should have a mock right now summary
    And issue "kanbus-jit-epic" should have a mock right now summary
    And stdout should contain "Mock right-now summary for kanbus-jit-task."
    And stdout should contain "Mock right-now summary for kanbus-jit-epic."

  Scenario: Now leaves a fresh cached summary in place
    Given an issue "kanbus-jit-cached" exists with title "Cached issue"
    And issue "kanbus-jit-cached" has right now summary "Cached summary."
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should contain "Cached summary."
    And issue "kanbus-jit-cached" should have right now summary "Cached summary."

  Scenario: Now skips generation when AI is unconfigured
    Given the Kanbus project has no AI configuration
    And an issue "kanbus-jit-offline" exists with title "Offline issue"
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should contain "(no right-now summary)"

  Scenario: Raw Now output does not backfill summaries
    Given an issue "kanbus-jit-raw" exists with title "Raw issue"
    When I run "kanbus now --status all --list --raw"
    Then the command should succeed
    And stdout should contain "Raw issue"
    And stdout should not contain "Mock right-now summary for kanbus-jit-raw."
    And issue "kanbus-jit-raw" should have no right now summary

  Scenario: Now backfills every active-tree descendant regardless of status
    Given an issue "kanbus-jit-live-parent" exists with status "in_progress"
    And an issue "kanbus-jit-live-child" of type "task" with status "closed" and parent "kanbus-jit-live-parent"
    When I run "kanbus now --list"
    Then the command should succeed
    And issue "kanbus-jit-live-parent" should have a mock right now summary
    And issue "kanbus-jit-live-child" should have a mock right now summary
    And stdout should contain "Mock right-now summary for kanbus-jit-live-parent."
    And stdout should contain "Mock right-now summary for kanbus-jit-live-child."
