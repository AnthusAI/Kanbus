@wip
Feature: Standup report shared stack on right-now summaries
  On-demand standup reports consume real board state from the same pipeline as
  `kbs now` / `kanbus now`. Standup generation never invents placeholder text and
  never forks a parallel LiteLLM client or model configuration.

  Product rules:
  - Standup gathers issue facts by running the recursive right-now path (JIT
    backfill included) for the requested scope before composing the report.
  - Omitting issue identifiers uses the same default selection as `kanbus now`
    without identifiers: status filter `in_progress`, reverse-chronological by
    `updated_at`, default cap of 30 issues. The fact feed includes the current
    project and every configured `virtual_projects` entry (congregation scope).
  - Explicit issue identifiers still narrow scope; `--no-recursive` limits to
    the named issues only (same as `kanbus now`).
  - If right-now summary generation cannot produce real summaries, standup fails
    closed with a clear error. No mock strings, "(no right-now summary)", or
    synthetic filler may appear in standup output.
  - Standup reuses the right-now AI configuration (`ai.provider`, product
    default model, and `right_now.model` override). It does not introduce a
    separate standup-specific LiteLLM client or secrets path.
  - Pudicus remains the commit gate; standup does not add a parallel quality
    program.

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"

  Scenario: Standup for a scoped issue uses recursive right-now summaries
    Given an issue "kanbus-stu-init" of type "initiative" with status "open" and parent "kanbus-stu-missing" and title "Standup initiative"
    And an issue "kanbus-stu-epic" of type "epic" with status "in_progress" and parent "kanbus-stu-init" and title "Standup epic"
    And an issue "kanbus-stu-task" of type "task" with status "in_progress" and parent "kanbus-stu-epic" and title "Standup task"
    When I run "kanbus standup kanbus-stu-init"
    Then the command should succeed
    And issue "kanbus-stu-task" should have a non-empty right now summary
    And issue "kanbus-stu-epic" should have a non-empty right now summary
    And issue "kanbus-stu-init" should have a non-empty right now summary
    And stdout should not contain "(no right-now summary)"
    And stdout should not contain "Mock right-now summary"

  Scenario: Standup without issue IDs uses kanbus now default in_progress selection
    Given an issue "kanbus-def-ip" exists with status "in_progress"
    And issue "kanbus-def-ip" has right now summary "Default scope work."
    And an issue "kanbus-def-open" exists with status "open"
    And issue "kanbus-def-open" has right now summary "Not in default scope."
    When I run "kanbus standup"
    Then the command should succeed
    And the standup fact feed should match kanbus now default listing
    And stdout should contain "Default scope work."
    And stdout should not contain "Not in default scope."

  Scenario: Standup without issue IDs respects kanbus now default cap of 30
    Given 31 in-progress issues exist with identifier prefix "kanbus-def-cap"
    When I run "kanbus standup"
    Then the command should succeed
    And the standup fact feed should have 30 issues
    And the standup fact feed should not include issue "kanbus-def-cap-31"

  Scenario: Standup fact feed includes in-progress issues from virtual projects
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-wip" exists in virtual project "alpha"
    And issue "alpha-wip" has status "in_progress"
    And issue "alpha-wip" has right now summary "Alpha project work."
    And an issue "kbs-wip" exists with status "in_progress"
    And issue "kbs-wip" has right now summary "Primary project work."
    When I run "kanbus standup"
    Then the command should succeed
    And the standup fact feed should include issue "alpha-wip"
    And the standup fact feed should include issue "kbs-wip"
    And stdout should contain "Alpha project work."
    And stdout should contain "Primary project work."

  Scenario: Standup fails closed when AI provider is not configured
    Given the Kanbus project has no AI configuration
    And an issue "kanbus-stu-offline" exists with title "Offline standup issue"
    When I run "kanbus standup kanbus-stu-offline"
    Then the command should fail
    And stderr should contain "Right-now summary generation requires ai.provider litellm in .kanbus.yml"
    And stdout should not contain "(no right-now summary)"
    And stdout should not contain "placeholder"

  Scenario: Standup output never contains mock right-now placeholder text
    Given an issue "kanbus-stu-clean" exists with title "Clean standup issue"
    And issue "kanbus-stu-clean" has right now summary "Shipping the standup spec."
    When I run "kanbus standup kanbus-stu-clean"
    Then the command should succeed
    And stdout should contain "Shipping the standup spec."
    And stdout should not contain "Mock right-now summary"
    And stdout should not contain "(no right-now summary)"

  Scenario: Standup reuses right-now model configuration without a parallel client
    Given a Kanbus project with a file "kanbus.yml" containing:
      """
      ai:
        provider: "litellm"
        model: "gpt-5.6-luna"
      right_now:
        model: "gpt-4o-mini"
      """
    And an issue "kanbus-stu-model" exists with title "Model reuse issue"
    When I run "kanbus standup kanbus-stu-model"
    Then the command should succeed
    And standup generation should use the right now litellm configuration
    And standup generation should not use a separate standup litellm client

  Scenario: Standup JSON output is structured report data with source_issues
    Given an issue "kanbus-stu-json" exists with status "in_progress"
    And issue "kanbus-stu-json" has right now summary "JSON standup source."
    When I run "kanbus standup kanbus-stu-json --json"
    Then the command should succeed
    And stdout should be valid JSON
    And the standup JSON output should include fields "profile,sections,source_issues"
    And the standup JSON source_issues should include issue "kanbus-stu-json"
