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

  Signal rules (observable; meeting-script uses calendar window with skip_weekends):
  - **Yesterday**: an issue appears when `closed_at` falls on a completed
    calendar day before report time, OR the issue event log has a
    `state_transition` to `closed` or `done` on a completed calendar day.
    Yesterday bullets cite the issue right-now summary text.
  - **Today**: an issue appears when its status is `in_progress` or `blocked`
    at report time AND the issue is in the standup fact feed. An issue MUST NOT
    appear in both Yesterday and Today.
  - **Blockers**: every fact-feed issue with status `blocked` appears here.
  - **Likely questions**: at least one question per blocked fact-feed issue,
    derived from that issue's right-now summary keywords; stale in-progress
    issues (`updated_at` older than lookback_hours) each add a staleness
    question naming the issue identifier.

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"

  Scenario: Default standup without issue IDs uses meeting-script on standup default selection
    Given an issue "kanbus-ms-def" exists with status "in_progress"
    And issue "kanbus-ms-def" has right now summary "Default meeting-script work."
    When I run "kanbus standup"
    Then the command should succeed
    And the standup report should have profile "meeting-script"
    And the standup fact feed should match standup default listing

  Scenario: Default standup uses meeting-script profile when scoped
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

  Scenario: Closed issue on completed calendar day appears in Yesterday not Today
    Given standup lookback hours is 24
    And an issue "kanbus-ms-yest" exists with status "closed"
    And issue "kanbus-ms-yest" closed on the previous calendar day in standup timezone
    And issue "kanbus-ms-yest" has right now summary "Finished API integration."
    And an issue "kanbus-ms-today" exists with status "in_progress"
    And issue "kanbus-ms-today" has right now summary "Continuing UI polish."
    When I run "kanbus standup kanbus-ms-yest kanbus-ms-today --profile meeting-script"
    Then the standup report section "Yesterday" should mention "Finished API integration"
    And the standup report section "Today" should mention "Continuing UI polish"
    And the standup report section "Today" should not mention "Finished API integration"

  Scenario: Status transition to closed on completed calendar day qualifies for Yesterday
    Given standup lookback hours is 24
    And an issue "kanbus-ms-trans" exists with status "closed"
    And issue "kanbus-ms-trans" has a state transition to "closed" on the previous calendar day in standup timezone
    And issue "kanbus-ms-trans" has right now summary "Merged the compaction spec."
    When I run "kanbus standup kanbus-ms-trans --profile meeting-script"
    Then the standup report section "Yesterday" should mention "Merged the compaction spec."
    And the standup report section "Today" should not mention "kanbus-ms-trans"

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

  Scenario: Likely questions derive from blocked work in the fact feed
    Given an issue "kanbus-ms-block-q" exists with status "blocked"
    And issue "kanbus-ms-block-q" has right now summary "Blocked on security review for OAuth scopes."
    When I run "kanbus standup kanbus-ms-block-q --profile meeting-script"
    Then the command should succeed
    And the standup report section "Likely questions" should mention "security review"
    And the standup report section "Likely questions" should mention "OAuth scopes"

  Scenario: Stale in-progress work surfaces in Close-out not Likely questions
    Given standup lookback hours is 24
    And an issue "kanbus-ms-stale" exists with status "in_progress"
    And issue "kanbus-ms-stale" has updated_at older than standup lookback
    And issue "kanbus-ms-stale" has right now summary "Waiting on review before deploy."
    When I run "kanbus standup kanbus-ms-stale --profile meeting-script"
    Then the command should succeed
    And the standup report section "Close-out" should mention "kanbus-ms-stale"
    And the standup report section "Likely questions" should not mention "Why is kanbus-ms-stale still in progress?"

  Scenario: Meeting script for recursive scope covers descendant work
    Given an issue "kanbus-ms-init" of type "initiative" with status "open" and parent "kanbus-ms-missing" and title "Meeting script initiative"
    And an issue "kanbus-ms-child" of type "task" with status "in_progress" and parent "kanbus-ms-init" and title "Child task"
    And issue "kanbus-ms-child" has right now summary "Child task in progress."
    When I run "kanbus standup kanbus-ms-init --profile meeting-script"
    Then the command should succeed
    And the standup report section "Today" should mention "Child task in progress."
