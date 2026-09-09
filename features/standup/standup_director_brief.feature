@wip
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

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Director brief profile is selectable
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

  Scenario: Director brief includes health and momentum sections
    Given an issue "kanbus-db-health" exists with status "in_progress"
    And issue "kanbus-db-health" has right now summary "Healthy forward progress."
    When I run "kanbus standup kanbus-db-health --profile director-brief"
    Then the command should succeed
    And the standup report should include section "Health"
    And the standup report should include section "Momentum"
    And the standup report should include section "Risks"
    And the standup report should include section "Blockers"

  Scenario: Director brief highlights blocked work as risk signal
    Given an issue "kanbus-db-risk" exists with status "blocked"
    And issue "kanbus-db-risk" has right now summary "Blocked on external dependency."
    When I run "kanbus standup kanbus-db-risk --profile director-brief"
    Then the command should succeed
    And the standup report section "Risks" should mention "kanbus-db-risk"
    And the standup report section "Blockers" should mention "external dependency"

  Scenario: Director brief and meeting script share the same underlying facts
    Given an issue "kanbus-db-shared" exists with status "in_progress"
    And issue "kanbus-db-shared" has right now summary "Shared fact line."
    When I run "kanbus standup kanbus-db-shared --profile meeting-script --json"
    Then the command should succeed
    And the standup JSON output should record source issue "kanbus-db-shared"
    When I run "kanbus standup kanbus-db-shared --profile director-brief --json"
    Then the command should succeed
    And the standup JSON output should record source issue "kanbus-db-shared"
    And the standup JSON source facts should match between profiles

  Scenario: Director brief fails closed when summaries are unavailable
    Given the Kanbus project has no AI configuration
    And an issue "kanbus-db-offline" exists with title "Offline director brief"
    When I run "kanbus standup kanbus-db-offline --profile director-brief"
    Then the command should fail
    And stderr should contain "Right-now summary generation requires ai.provider litellm in .kanbus.yml"
    And stdout should not contain "Health"
    And stdout should not contain "placeholder"
