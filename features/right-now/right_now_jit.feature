Feature: Right now just-in-time backfill
  As a Kanbus user
  I want missing right-now summaries generated when I look at Now
  So that the feed always shows real summaries or fails clearly

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Now backfills a missing summary
    Given an issue "kanbus-jit1" exists with title "Needs a summary"
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should not contain "(no right-now summary)"
    And issue "kanbus-jit1" should have a non-empty right now summary

  Scenario: Now backfills children before the parent
    Given an issue "kanbus-jit-epic" of type "epic" with status "open" and title "Parent epic"
    And an issue "kanbus-jit-task" of type "task" with status "open" and parent "kanbus-jit-epic"
    When I run "kanbus now kanbus-jit-epic"
    Then the command should succeed
    And issue "kanbus-jit-task" should have a non-empty right now summary
    And issue "kanbus-jit-epic" should have a non-empty right now summary
    And stdout should not contain "(no right-now summary)"

  Scenario: Now leaves a fresh cached summary in place
    Given an issue "kanbus-jit-cached" exists with title "Cached issue"
    And issue "kanbus-jit-cached" has right now summary "Cached summary."
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should contain "Cached summary."
    And issue "kanbus-jit-cached" should have right now summary "Cached summary."

  Scenario: Now fails when AI is unconfigured
    Given the Kanbus project has no AI configuration
    And an issue "kanbus-jit-offline" exists with title "Offline issue"
    When I run "kanbus now --status all --list"
    Then the command should fail
    And stderr should contain "Right-now summary generation requires ai.provider litellm in .kanbus.yml"
    And stdout should not contain "(no right-now summary)"

  Scenario: Now regenerates a persisted mock summary
    Given right now generation uses completion "Regenerated production summary."
    And an issue "kanbus-jit-mock" exists with title "Mock persisted issue"
    And issue "kanbus-jit-mock" has right now summary "Mock right-now summary for kanbus-jit-mock."
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should contain "Regenerated production summary."
    And stdout should not contain "Mock right-now summary for kanbus-jit-mock."
    And issue "kanbus-jit-mock" should have right now summary "Regenerated production summary."

  Scenario: Raw Now output does not backfill summaries
    Given an issue "kanbus-jit-raw" exists with title "Raw issue"
    When I run "kanbus now --status all --list --raw"
    Then the command should succeed
    And stdout should contain "Raw issue"
    And issue "kanbus-jit-raw" should have no right now summary

  Scenario: Now listing does not backfill closed descendants
    Given an issue "kanbus-jit-live-parent" exists with status "in_progress"
    And an issue "kanbus-jit-live-child" of type "task" with status "closed" and parent "kanbus-jit-live-parent"
    When I run "kanbus now --list"
    Then the command should succeed
    And issue "kanbus-jit-live-parent" should have a non-empty right now summary
    And issue "kanbus-jit-live-child" should have no right now summary
    And stdout should not contain "(no right-now summary)"

  Scenario: Purge clears right-now summaries across the board
    Given an issue "kanbus-jit-purge-a" exists with title "Purge alpha"
    And issue "kanbus-jit-purge-a" has right now summary "Alpha summary."
    And an issue "kanbus-jit-purge-b" exists with title "Purge beta"
    And issue "kanbus-jit-purge-b" has right now summary "Beta summary."
    When I run "kanbus now --purge"
    Then the command should succeed
    And stdout should contain "Purged right-now summaries for 2 issues"
    And issue "kanbus-jit-purge-a" should have no right now summary
    And issue "kanbus-jit-purge-b" should have no right now summary
    And issue "kanbus-jit-purge-a" should have no right now updated at
    And issue "kanbus-jit-purge-b" should have no right now updated at
