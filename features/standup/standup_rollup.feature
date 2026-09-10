Feature: Standup rollup shapes and WIP close-out
  Multi-project congregation standups must roll up right-now facts instead of
  dumping every leaf as a flat Today bullet. Close-out surfaces cards that are
  ready to finish; empty Yesterday must never look broken.

  Rollup modes (`--rollup`):
  - **flat**: one Today bullet per fact-feed leaf (legacy single-project default).
  - **project**: one Today bullet per project partition, prefixed with the
    canonical congregation display label (from `virtual_projects.display_name` or
    congregation `name`, never mixed aliases for the same partition), using
    bottom-up LLM rollup of right-now facts (not semicolon-joined leaf text).
  - **tree**: nested Today lines (two-space indent per depth) grouped by project
    label on each forest root; parent lines use upward LLM rollup when multiple
    distinct child summaries exist.

  Canonical project labels:
  - One stable bracket label per virtual project partition per report.
  - Prefer `virtual_projects.<key>.display_name` (or `label`) over raw map keys.
  - Primary congregation partition uses `name` from `.kanbus.yml` when set, else
    `project_key`. Custom `project_label` on issues is normalized to the partition
    key before display resolution so `[Chattic.us]` and `[chatticus]` never both appear.

  Default rollup when `--rollup` is omitted:
  - **virtual_projects** congregation (board-wide, no issue IDs): `project`.
  - **single-project** board (no virtual_projects): `flat` for backward-compatible
    board-wide output; explicit issue scope with `--recursive` (default): `tree`.

  Close-out (meeting-script and director-brief):
  - Merged-but-still-`in_progress` issues (right-now mentions merge/PR).
  - Ready-to-close in-progress issues (right-now readiness phrasing).
  - Blocked issues waiting only on external parties.
  - Narrow stale WIP: in-progress beyond lookback with finishable close-out phrasing
    (for example waiting on review or deploy) and no recent descendant activity within
    lookback. Quiet in-progress epics without those signals stay out of Close-out.
  - Close-out is capped (default 6 bullets) with merged/ready items prioritized so the
    section stays actionable.
  - Likely questions must not ask why an issue is still in progress when it is already
    listed in Close-out.

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

  Scenario: Congregation Today uses canonical display labels for partitions
    Given a Kanbus project with virtual projects configured
    And virtual project "alpha" has display name "Alpha Pod"
    And congregation primary display name is "Kanbus"
    And an issue "alpha-wip" exists in virtual project "alpha"
    And issue "alpha-wip" has status "in_progress"
    And issue "alpha-wip" has right now summary "Alpha delivery."
    And an issue "kbs-wip" exists with status "in_progress"
    And issue "kbs-wip" has right now summary "Kanbus core delivery."
    When I run "kanbus standup"
    Then the command should succeed
    And the standup report section "Today" should mention "[Alpha Pod]"
    And the standup report section "Today" should not mention "[alpha]"
    And the standup report section "Today" should mention "[Kanbus]"

  Scenario: Project rollup synthesizes multiple roots via upward LLM reduce
    Given an issue "kanbus-pr-a" of type "epic" with status "in_progress" and parent "kanbus-pr-missing" and title "Rollup A"
    And issue "kanbus-pr-a" has right now summary "Alpha track shipping."
    And an issue "kanbus-pr-b" of type "epic" with status "in_progress" and parent "kanbus-pr-missing-b" and title "Rollup B"
    And issue "kanbus-pr-b" has right now summary "Beta track hardening."
    And standup rollup reduce uses completion "Alpha and Beta tracks in flight this week."
    When I run "kanbus standup kanbus-pr-a kanbus-pr-b --rollup project"
    Then the command should succeed
    And the standup report section "Today" should mention "Alpha and Beta tracks in flight this week."
    And the standup report section "Today" should not contain ";"

  Scenario: Tree rollup nests parent and child with indentation
    Given an issue "kanbus-tr-init" of type "initiative" with status "open" and parent "kanbus-tr-missing" and title "Tree rollup initiative"
    And issue "kanbus-tr-init" has right now summary "Initiative rollup summary."
    And an issue "kanbus-tr-child" of type "task" with status "in_progress" and parent "kanbus-tr-init" and title "Tree child"
    And issue "kanbus-tr-child" has right now summary "Child leaf work."
    And standup rollup reduce uses completion "Initiative rollup summary."
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

  Scenario: Finishable stale WIP appears in Close-out not Likely questions
    Given standup lookback hours is 24
    And an issue "kanbus-co-stale" exists with status "in_progress"
    And issue "kanbus-co-stale" has updated_at older than standup lookback
    And issue "kanbus-co-stale" has right now summary "Waiting on review; no deploy yet."
    When I run "kanbus standup kanbus-co-stale --profile meeting-script"
    Then the command should succeed
    And the standup report section "Close-out" should mention "kanbus-co-stale"
    And the standup report section "Likely questions" should not mention "Why is kanbus-co-stale still in progress?"

  Scenario: Quiet in-progress work without finishable signals stays out of Close-out
    Given standup lookback hours is 24
    And an issue "kanbus-co-quiet" exists with status "in_progress"
    And issue "kanbus-co-quiet" has updated_at older than standup lookback
    And issue "kanbus-co-quiet" has right now summary "Long-running refactor."
    When I run "kanbus standup kanbus-co-quiet --profile meeting-script"
    Then the command should succeed
    And the standup report section "Close-out" should not mention "kanbus-co-quiet"

  Scenario: Director brief Momentum respects project rollup on virtual_projects
    Given a Kanbus project with virtual projects configured
    And virtual project "alpha" has display name "Alpha Pod"
    And an issue "alpha-mom" exists in virtual project "alpha"
    And issue "alpha-mom" has status "in_progress"
    And issue "alpha-mom" has updated_at within standup lookback
    And issue "alpha-mom" has right now summary "Alpha momentum line."
    And an issue "kbs-mom" exists with status "in_progress"
    And issue "kbs-mom" has updated_at within standup lookback
    And issue "kbs-mom" has right now summary "Kanbus momentum line."
    When I run "kanbus standup --profile director-brief"
    Then the command should succeed
    And the standup report section "Momentum" should mention "[Alpha Pod]"
    And the standup report section "Momentum" should mention "Alpha momentum line."
