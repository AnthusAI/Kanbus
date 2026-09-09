Feature: Whole-project right-now payload for agent compaction hooks
  Coding-agent compaction hooks reinject board awareness after context compaction.
  This feature defines the authoritative CLI payload contract that hook installers
  consume. Hook installer implementation is out of scope here.

  Product rules:
  - Compaction injection uses whole-project WIP from `kbs now` / `kanbus now` (capped),
    without issue-identifier arguments. Pinned-issue scoped output is never the
    compaction payload.
  - On-demand agents may call `kbs now <issue-id>` for focused WIP. That mode is
    separate from compaction reinjection.
  - Hook wrappers must soft-fail when `kbs now` fails or times out: the agent
    session continues even though the CLI may exit non-zero. Only the hook wrapper
    applies soft-fail; the CLI itself is unchanged.
  - Payload items must expose issue key, title, status, priority, and right-now
    sentence for a short injected reminder. Structured flat JSON is preferred;
    compact `--list` text is acceptable for platforms that accept stdout text.

  Hook-oriented invocation (stable contract):
  `kanbus now --json --list`

  Platform notes (documentation sketch; installers are out of scope):
  - Claude Code: SessionStart matcher `compact` via `.claude/settings.json`; stdout
    plain text or JSON `hookSpecificOutput.additionalContext`. PreCompact and
    PostCompact are not the reinject path.
  - Cursor: `preCompact` in `.cursor/hooks.json` is observational only and cannot
    reinject agent context post-compact. v1 uses on-demand `kbs now` in AGENTS.md
    plus an optional preCompact nudge.
  - Codex: SessionStart matcher source `compact`; stdout or `additionalContext`.
  - Antigravity: no compaction reinject event in IDE hooks; v1 is on-demand docs
    only. Do not use PreInvocation every-turn inject for compaction v1.

  Rationale: JIT short programmatic guidance (AnthusAI/Elicitation-Guidance thesis).

  Background:
    Given a Kanbus project with default configuration

  Scenario: Compaction payload is whole-project board listing without issue identifiers
    Given an issue "kanbus-cmp-a" exists with status "in_progress"
    And an issue "kanbus-cmp-b" exists with status "in_progress"
    When I run "kanbus now --json --list"
    Then the command should succeed
    And stdout should be valid JSON
    And the right now JSON output should have 2 items
    And the right now JSON item for "kanbus-cmp-a" should include fields "id,title,type,status,priority,updated_at,right_now_summary,parent"
    And the right now JSON item for "kanbus-cmp-b" should include fields "id,title,type,status,priority,updated_at,right_now_summary,parent"

  Scenario: Compaction JSON items include priority for reminder rendering
    Given an issue "kanbus-cmp-pri" exists with status "in_progress"
    And issue "kanbus-cmp-pri" has priority 1
    And issue "kanbus-cmp-pri" has right now summary "Shipping compaction payload spec."
    When I run "kanbus now --json --list"
    Then the command should succeed
    And the right now JSON item for "kanbus-cmp-pri" should have priority 1
    And the right now JSON item for "kanbus-cmp-pri" should have right_now_summary "Shipping compaction payload spec."

  Scenario: Compaction payload uses default whole-project cap
    Given 31 in-progress issues exist with identifier prefix "kanbus-cmp-cap"
    When I run "kanbus now --json --list"
    Then the command should succeed
    And the right now JSON output should have 30 items
    And stdout should not contain "kanbus-cmp-cap-31"

  Scenario: Compaction compact text list includes title and right-now summary
    Given an issue "kanbus-cmp-txt" exists with status "in_progress"
    And issue "kanbus-cmp-txt" has right now summary "Compact reminder line."
    When I run "kanbus now --list"
    Then the command should succeed
    And stdout should contain "kanbus-cmp-txt"
    And stdout should contain "Compact reminder line."

  Scenario: On-demand scoped now is separate from compaction whole-project payload
    Given an issue "kanbus-cmp-focus" exists with status "in_progress"
    And issue "kanbus-cmp-focus" has right now summary "Focused WIP."
    And an issue "kanbus-cmp-other" exists with status "in_progress"
    And issue "kanbus-cmp-other" has right now summary "Other WIP."
    When I run "kanbus now kanbus-cmp-focus"
    Then the command should succeed
    And stdout should contain "kanbus-cmp-focus"
    And stdout should contain "Focused WIP."
    And stdout should not contain "kanbus-cmp-other"
    And stdout should not contain "Other WIP."
