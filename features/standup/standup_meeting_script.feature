@wip
Feature: Standup meeting script profile
  As a Kanbus user preparing for a daily standup
  I want a first-person speakable script with very short bullets
  So that I can read it aloud without rewriting paragraphs

  The meeting-script profile transforms the same underlying right-now facts as
  director-brief, but the voice, section headings, and bullet length target
  spoken delivery.

  Expected sections (stable contract):
  - Yesterday
  - Today
  - Blockers
  - Likely questions

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Default standup uses meeting-script profile
    Given an issue "kanbus-ms-default" exists with status "in_progress"
    And issue "kanbus-ms-default" has right now summary "Default profile work."
    When I run "kanbus standup kanbus-ms-default"
    Then the command should succeed
    And the standup report should have profile "meeting-script"
    And the standup report should include section "Yesterday"
    And the standup report should include section "Today"
    And the standup report should include section "Blockers"
    And the standup report should include section "Likely questions"

  Scenario: Explicit meeting-script flag selects the profile
    Given an issue "kanbus-ms-explicit" exists with status "in_progress"
    And issue "kanbus-ms-explicit" has right now summary "Explicit profile work."
    When I run "kanbus standup kanbus-ms-explicit --profile meeting-script"
    Then the command should succeed
    And the standup report should have profile "meeting-script"

  Scenario: Meeting script uses first-person speakable voice
    Given an issue "kanbus-ms-voice" exists with status "in_progress"
    And issue "kanbus-ms-voice" has right now summary "Voice check work."
    When I run "kanbus standup kanbus-ms-voice --profile meeting-script"
    Then the command should succeed
    And the standup report should use first person voice
    And the standup report should not use third person executive voice

  Scenario: Meeting script bullets stay short for spoken delivery
    Given an issue "kanbus-ms-short" exists with status "in_progress"
    And issue "kanbus-ms-short" has right now summary "Short bullet work."
    When I run "kanbus standup kanbus-ms-short --profile meeting-script"
    Then the command should succeed
    And each standup report bullet should be at most 120 characters

  Scenario: Meeting script surfaces blockers from underlying facts
    Given an issue "kanbus-ms-blocked" exists with status "blocked"
    And issue "kanbus-ms-blocked" has right now summary "Waiting on upstream API."
    When I run "kanbus standup kanbus-ms-blocked --profile meeting-script"
    Then the command should succeed
    And the standup report section "Blockers" should mention "kanbus-ms-blocked"
    And the standup report section "Blockers" should not be empty

  Scenario: Meeting script for recursive scope covers descendant work
    Given an issue "kanbus-ms-init" of type "initiative" with status "open" and parent "kanbus-ms-missing" and title "Meeting script initiative"
    And an issue "kanbus-ms-child" of type "task" with status "in_progress" and parent "kanbus-ms-init" and title "Child task"
    And issue "kanbus-ms-child" has right now summary "Child task in progress."
    When I run "kanbus standup kanbus-ms-init --profile meeting-script"
    Then the command should succeed
    And the standup report section "Today" should mention "Child task in progress."
