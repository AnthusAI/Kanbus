Feature: Standup rollup shapes and WIP close-out
  Multi-project congregation standups must roll up right-now facts instead of
  dumping every leaf as a flat Today bullet. Close-out surfaces cards that are
  ready to finish; empty Yesterday must never look broken.

  Rollup modes (`--rollup`):
  - **flat**: one Today bullet per fact-feed leaf (legacy single-project default).
  - **project**: one Today bullet per project partition, prefixed with the
    project label, using upward-rolled right-now text from that project's WIP roots.
  - **tree**: nested Today lines (two-space indent per depth) grouped by project
    label on each forest root.

  Default rollup when `--rollup` is omitted:
  - **virtual_projects** congregation (board-wide, no issue IDs): `project`.
  - **single-project** board (no virtual_projects): `flat` for backward-compatible
    board-wide output; explicit issue scope with `--recursive` (default): `tree`.

  Close-out (meeting-script and director-brief):
  - Merged-but-still-`in_progress` issues (right-now mentions merge/PR).
  - Ready-to-close in-progress issues (right-now readiness phrasing).
  - Blocked issues waiting only on external parties.
  - Stale in-progress WIP from lookback rules moves here instead of Likely questions.

  Yesterday:
  - When no completions qualify, emit exactly one bullet: `No completions yesterday.`

  Dedup:
  - Parent and child Today bullets with identical or near-identical right-now text
    must not both appear in tree rollup.

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"

  Scenario: Board-wide virtual_projects default uses project rollup with labels
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-wip" exists in virtual project "alpha"
    And issue "alpha-wip" has status "in_progress"
    And issue "alpha-wip" has right now summary "Alpha delivery in flight."
    And an issue "kbs-wip" exists with status "in_progress"
    And issue "kbs-wip" has right now summary "Kanbus core delivery."
    When I run "kanbus standup"
    Then the command should succeed
    And the standup report section "Today" should mention "[alpha]"
    And the standup report section "Today" should mention "[kanbus]"
    And the standup report section "Today" should mention "Alpha delivery in flight."
    And the standup report section "Today" should mention "Kanbus core delivery."

  Scenario: Explicit project rollup on virtual_projects congregation
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-roll" exists in virtual project "alpha"
    And issue "alpha-roll" has status "in_progress"
    And issue "alpha-roll" has right now summary "Alpha rollup leaf."
    When I run "kanbus standup --rollup project"
    Then the command should succeed
    And the standup report section "Today" should mention "[alpha]"

  Scenario: Tree rollup nests parent and child with indentation
    Given an issue "kanbus-tr-init" of type "initiative" with status "open" and parent "kanbus-tr-missing" and title "Tree rollup initiative"
    And issue "kanbus-tr-init" has right now summary "Initiative rollup summary."
    And an issue "kanbus-tr-child" of type "task" with status "in_progress" and parent "kanbus-tr-init" and title "Tree child"
    And issue "kanbus-tr-child" has right now summary "Child leaf work."
    When I run "kanbus standup kanbus-tr-init --rollup tree"
    Then the command should succeed
    And the standup report section "Today" should mention "Initiative rollup summary."
    And the standup report section "Today" should mention "Child leaf work."
    And the standup report section "Today" should match pattern "  Child leaf work."

  Scenario: Tree rollup drops duplicate parent and child summaries
    Given an issue "kanbus-tr-dup-parent" of type "epic" with status "in_progress" and parent "kanbus-tr-dup-missing" and title "Dup parent"
    And issue "kanbus-tr-dup-parent" has right now summary "Same rollup line."
    And an issue "kanbus-tr-dup-child" of type "task" with status "in_progress" and parent "kanbus-tr-dup-parent" and title "Dup child"
    And issue "kanbus-tr-dup-child" has right now summary "Same rollup line."
    When I run "kanbus standup kanbus-tr-dup-parent --rollup tree"
    Then the command should succeed
    And the standup report section "Today" should mention "Same rollup line."
    And the standup report section "Today" should have 1 bullet

  Scenario: Empty Yesterday states no completions explicitly
    Given an issue "kanbus-empty-today" exists with status "in_progress"
    And issue "kanbus-empty-today" has right now summary "Only today work."
    When I run "kanbus standup kanbus-empty-today"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "No completions yesterday."

  Scenario: Close-out surfaces merged still in progress
    Given an issue "kanbus-co-merge" exists with status "in_progress"
    And issue "kanbus-co-merge" has right now summary "PR merged; waiting on deploy toggle."
    When I run "kanbus standup kanbus-co-merge"
    Then the command should succeed
    And the standup report should include section "Close-out"
    And the standup report section "Close-out" should mention "kanbus-co-merge"

  Scenario: Stale WIP appears in Close-out not Likely questions
    Given standup lookback hours is 24
    And an issue "kanbus-co-stale" exists with status "in_progress"
    And issue "kanbus-co-stale" has updated_at older than standup lookback
    And issue "kanbus-co-stale" has right now summary "Long-running refactor."
    When I run "kanbus standup kanbus-co-stale --profile meeting-script"
    Then the command should succeed
    And the standup report section "Close-out" should mention "kanbus-co-stale"
    And the standup report section "Likely questions" should not mention "Why is kanbus-co-stale still in progress?"
