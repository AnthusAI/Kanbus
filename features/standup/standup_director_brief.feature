Feature: Standup director brief profile
  As a stakeholder scanning project health
  I want an executive brief from the same board facts as the meeting script
  So that I can assess momentum and risk without first-person speaking notes

  The director-brief profile consumes identical right-now inputs but frames
  health, momentum, risks, and blockers for stakeholders. It is not written as
  speakable first-person bullets.

  Expected sections (stable contract):
  - Health
  - Momentum
  - Risks
  - Blockers

  Signal rules (observable; default `standup.lookback_hours` is 24):
  - **Health**: aggregate counts from the fact feed only — number of issues with
    status `in_progress` and number with status `blocked`. Health MUST NOT
    include first-person phrasing or per-issue narrative bullets.
  - **Momentum**: lists issue identifiers that had forward progress within
    lookback_hours: `state_transition` to `in_progress`, OR to `closed`/`done`,
    OR `updated_at` within lookback while status is `in_progress`. Momentum
    bullets cite the issue right-now summary text.
  - **Risks**: every fact-feed issue with status `blocked`, plus any in-progress
    issue whose `updated_at` is older than lookback_hours (stale WIP).
  - **Blockers**: same membership as meeting-script Blockers — every blocked
    fact-feed issue with its right-now summary text.

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"

  Scenario: Director brief without issue IDs covers board-wide congregation scope
    Given an issue "kanbus-db-board" exists with status "in_progress"
    And issue "kanbus-db-board" has right now summary "Board-wide brief work."
    And an issue "kanbus-db-open" exists with status "open"
    When I run "kanbus standup --profile director-brief"
    Then the command should succeed
    And the standup report should have profile "director-brief"
    And the standup fact feed should match standup default listing
    And stdout should contain "Board-wide brief work."

  Scenario: Director brief profile is selectable with explicit scope
    Given an issue "kanbus-db-select" exists with status "in_progress"
    And issue "kanbus-db-select" has right now summary "Director brief work."
    When I run "kanbus standup kanbus-db-select --profile director-brief"
    Then the command should succeed
    And the standup report should have profile "director-brief"

  Scenario: Director brief uses stakeholder framing not first-person voice
    Given an issue "kanbus-db-voice" exists with status "in_progress"
    And issue "kanbus-db-voice" has right now summary "Stakeholder voice check."
    When I run "kanbus standup kanbus-db-voice --profile director-brief"
    Then the command should succeed
    And the standup report should use third person executive voice
    And the standup report should not use first person voice

  Scenario: Health reports in-progress and blocked counts from the fact feed
    Given an issue "kanbus-db-ip1" exists with status "in_progress"
    And an issue "kanbus-db-ip2" exists with status "in_progress"
    And an issue "kanbus-db-blk" exists with status "blocked"
    When I run "kanbus standup kanbus-db-ip1 kanbus-db-ip2 kanbus-db-blk --profile director-brief"
    Then the command should succeed
    And the standup report section "Health" should report 2 in-progress issues
    And the standup report section "Health" should report 1 blocked issue

  Scenario: Momentum lists issues with recent forward transitions
    Given standup lookback hours is 24
    And an issue "kanbus-db-mom" exists with status "closed"
    And issue "kanbus-db-mom" has closed_at within standup lookback
    And issue "kanbus-db-mom" has right now summary "Completed rollout."
    When I run "kanbus standup kanbus-db-mom --profile director-brief --rollup flat"
    Then the command should succeed
    And the standup report section "Momentum" should mention "kanbus-db-mom"
    And the standup report section "Momentum" should mention "Completed rollout"

  Scenario: Momentum includes in-progress issues updated within lookback
    Given standup lookback hours is 24
    And an issue "kanbus-db-recent" exists with status "in_progress"
    And issue "kanbus-db-recent" has updated_at within standup lookback
    And issue "kanbus-db-recent" has right now summary "Active delivery this week."
    When I run "kanbus standup kanbus-db-recent --profile director-brief --rollup flat"
    Then the command should succeed
    And the standup report section "Momentum" should mention "kanbus-db-recent"
    And the standup report section "Momentum" should mention "Active delivery this week"

  Scenario: Director brief highlights blocked work as risk signal
    Given an issue "kanbus-db-risk" exists with status "blocked"
    And issue "kanbus-db-risk" has right now summary "Blocked on external dependency."
    When I run "kanbus standup kanbus-db-risk --profile director-brief"
    Then the command should succeed
    And the standup report section "Risks" should mention "kanbus-db-risk"
    And the standup report section "Blockers" should mention "external dependency"

  Scenario: Stale in-progress work surfaces in Risks not Momentum
    Given standup lookback hours is 24
    And an issue "kanbus-db-stale" exists with status "in_progress"
    And issue "kanbus-db-stale" has updated_at older than standup lookback
    And issue "kanbus-db-stale" has right now summary "Stalled refactor."
    When I run "kanbus standup kanbus-db-stale --profile director-brief"
    Then the command should succeed
    And the standup report section "Risks" should mention "kanbus-db-stale"
    And the standup report section "Momentum" should not mention "kanbus-db-stale"

  Scenario: Director brief and meeting script share source_issues and right_now texts
    Given an issue "kanbus-db-shared" exists with status "in_progress"
    And issue "kanbus-db-shared" has right now summary "Shared fact line."
    When I run "kanbus standup kanbus-db-shared --profile meeting-script --json"
    Then the command should succeed
    And the standup JSON output should record source issue "kanbus-db-shared"
    When I run "kanbus standup kanbus-db-shared --profile director-brief --json"
    Then the command should succeed
    And the standup JSON output should record source issue "kanbus-db-shared"
    And the standup JSON source_issues set should match between profiles
    And the standup JSON right_now_texts should match between profiles

  Scenario: Director brief fails closed when summaries are unavailable
    Given the Kanbus project has no AI configuration
    And an issue "kanbus-db-offline" exists with title "Offline director brief"
    When I run "kanbus standup kanbus-db-offline --profile director-brief"
    Then the command should fail
    And stderr should contain "Right-now summary generation requires ai.provider litellm in .kanbus.yml"
    And stdout should not contain "Health"
    And stdout should not contain "placeholder"
