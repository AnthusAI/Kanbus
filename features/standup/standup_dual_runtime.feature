@wip
Feature: Standup report dual-runtime parity
  Kanbus ships standup report generation in both Python and Rust CLIs.
  Both implementations must satisfy the same observable behavior defined by the
  standup feature files in features/standup/ and features/cli/standup.feature.

  Parity contract (non-negotiable):
  - Identical CLI surface: command name, flags, profile names, and JSON schema.
  - Identical exit codes for success and each failure mode.
  - Identical stderr error messages byte-for-byte (including right-now fail-closed text).
  - Identical stdout formatting for the same fixture project and profile.
  - No implementation may bypass the shared right-now stack or emit placeholders
    that the other runtime would reject.

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Both runtimes expose the standup command with the same profiles
    When I run "kanbus standup --help"
    Then the command should succeed
    And stdout should contain "standup"
    And stdout should contain "meeting-script"
    And stdout should contain "director-brief"
    And stdout should contain "--profile"
    And stdout should contain "--json"

  Scenario: Both runtimes fail with the same error when AI is unconfigured
    Given the Kanbus project has no AI configuration
    And an issue "kanbus-par-offline" exists with title "Parity offline issue"
    When I run "kanbus standup kanbus-par-offline"
    Then the command should fail with exit code 1
    And stderr should contain "Right-now summary generation requires ai.provider litellm in .kanbus.yml"

  Scenario: Both runtimes reject unknown standup profiles identically
    Given an issue "kanbus-par-badprof" exists with title "Bad profile issue"
    When I run "kanbus standup kanbus-par-badprof --profile unknown-profile"
    Then the command should fail with exit code 1
    And stderr should contain "unknown standup profile"

  Scenario: Both runtimes emit the same JSON schema for meeting-script
    Given an issue "kanbus-par-json" exists with status "in_progress"
    And issue "kanbus-par-json" has right now summary "Parity JSON source."
    When I run "kanbus standup kanbus-par-json --profile meeting-script --json"
    Then the command should succeed
    And stdout should be valid JSON
    And the standup JSON output should include fields "profile,sections,source_issues"

  Scenario: Both runtimes emit the same JSON schema for director-brief
    Given an issue "kanbus-par-djson" exists with status "in_progress"
    And issue "kanbus-par-djson" has right now summary "Director JSON source."
    When I run "kanbus standup kanbus-par-djson --profile director-brief --json"
    Then the command should succeed
    And stdout should be valid JSON
    And the standup JSON output should include fields "profile,sections,source_issues"

  Scenario: Removing wip from standup scenarios requires both implementations green
    Given standup parity is tracked by tools/check_spec_parity.py
    Then standup scenarios should not be considered complete until both Python behave and Rust cucumber pass without wip tags
