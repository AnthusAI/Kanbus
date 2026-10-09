Feature: Right now summaries are not generated on mutation
  As a Kanbus user
  I want board-mutating commands to make no LLM calls
  So that summaries cost money only when I look at Now

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Creating an issue does not generate a right now summary
    When I run "kanbus create Lazy create test"
    And I capture the issue identifier
    Then the command should succeed
    And the created issue should have no right now summary
    And the LLM usage log should not contain a right_now_summary entry

  Scenario: Updating an issue field keeps the prior right now summary
    Given an issue "kanbus-lazy01" exists with title "Update target"
    And issue "kanbus-lazy01" has right now summary "Prior summary text."
    When I run "kanbus update kanbus-lazy01 --description \"Changed description\""
    Then the command should succeed
    And issue "kanbus-lazy01" should have right now summary "Prior summary text."
    And the LLM usage log should not contain a right_now_summary entry

  Scenario: Adding a comment keeps the prior right now summary
    Given an issue "kanbus-lazy02" exists with title "Comment target"
    And issue "kanbus-lazy02" has right now summary "Prior summary text."
    When I add a comment to issue "kanbus-lazy02" with text "New activity note"
    Then the command should succeed
    And issue "kanbus-lazy02" should have right now summary "Prior summary text."
    And the LLM usage log should not contain a right_now_summary entry

  Scenario: Adding a dependency keeps the prior right now summary
    Given an issue "kanbus-lazy-dep-src" exists with title "Dependency source"
    And an issue "kanbus-lazy-dep-tgt" exists with title "Dependency target"
    And issue "kanbus-lazy-dep-src" has right now summary "Prior summary text."
    When I run "kanbus dep kanbus-lazy-dep-src blocked-by kanbus-lazy-dep-tgt"
    Then the command should succeed
    And issue "kanbus-lazy-dep-src" should have right now summary "Prior summary text."
    And the LLM usage log should not contain a right_now_summary entry

  Scenario: Deleting an issue keeps the parent right now summary
    Given an issue "kanbus-lazy-parent" of type "epic" with status "open" and title "Parent epic"
    And an issue "kanbus-lazy-child" of type "task" with status "open" and parent "kanbus-lazy-parent"
    And issue "kanbus-lazy-parent" has right now summary "Prior parent summary."
    When I run "kanbus delete kanbus-lazy-child --yes"
    Then the command should succeed
    And issue "kanbus-lazy-parent" should have right now summary "Prior parent summary."
    And the LLM usage log should not contain a right_now_summary entry

  Scenario: Changing a task status does not regenerate ancestor summaries
    Given an issue "kanbus-lazy-init" of type "initiative" with status "open"
    And an issue "kanbus-lazy-epic" of type "epic" with status "open" and parent "kanbus-lazy-init"
    And an issue "kanbus-lazy-task" of type "task" with status "open" and parent "kanbus-lazy-epic"
    And issue "kanbus-lazy-epic" has right now summary "Prior epic summary."
    And issue "kanbus-lazy-init" has right now summary "Prior initiative summary."
    When I update issue "kanbus-lazy-task" to status "in_progress"
    Then the command should succeed
    And issue "kanbus-lazy-task" should have no right now summary
    And issue "kanbus-lazy-epic" should have right now summary "Prior epic summary."
    And issue "kanbus-lazy-init" should have right now summary "Prior initiative summary."
    And the LLM usage log should not contain a right_now_summary entry

  Scenario: Now regenerates a summary made stale by a mutation
    Given an issue "kanbus-lazy-stale" exists with title "Stale target"
    And issue "kanbus-lazy-stale" has right now summary "Prior summary text."
    And issue "kanbus-lazy-stale" has right now updated at "2020-01-01T00:00:00Z"
    And issue "kanbus-lazy-stale" right now state is recorded
    When I update issue "kanbus-lazy-stale" to status "in_progress"
    Then the command should succeed
    And issue "kanbus-lazy-stale" should have right now summary "Prior summary text."
    When I run "kanbus now kanbus-lazy-stale --list"
    Then the command should succeed
    And issue "kanbus-lazy-stale" should have a mock right now summary
    And issue "kanbus-lazy-stale" right now summary should be refreshed

  Scenario: Now regenerates a parent summary when a direct child changed after it
    Given an issue "kanbus-lazy-roll-epic" of type "epic" with status "open" and title "Rollup epic"
    And an issue "kanbus-lazy-roll-task" of type "task" with status "open" and parent "kanbus-lazy-roll-epic"
    And issue "kanbus-lazy-roll-epic" was updated 4000 days ago
    And issue "kanbus-lazy-roll-epic" has right now summary "Prior epic summary."
    And issue "kanbus-lazy-roll-epic" has right now updated at "2020-01-01T00:00:00Z"
    And issue "kanbus-lazy-roll-epic" right now state is recorded
    When I add a comment to issue "kanbus-lazy-roll-task" with text "Child progress note"
    Then the command should succeed
    When I run "kanbus now kanbus-lazy-roll-epic --no-recursive --list"
    Then the command should succeed
    And issue "kanbus-lazy-roll-epic" should have a mock right now summary
    And issue "kanbus-lazy-roll-epic" right now summary should be refreshed

  Scenario: Now keeps a parent summary when no direct child changed after it
    Given an issue "kanbus-lazy-quiet-epic" of type "epic" with status "open" and title "Quiet epic"
    And an issue "kanbus-lazy-quiet-task" of type "task" with status "open" and parent "kanbus-lazy-quiet-epic"
    And issue "kanbus-lazy-quiet-epic" was updated 4000 days ago
    And issue "kanbus-lazy-quiet-task" was updated 4000 days ago
    And issue "kanbus-lazy-quiet-epic" has right now summary "Quiet epic summary."
    And issue "kanbus-lazy-quiet-epic" has right now updated at "2020-01-01T00:00:00Z"
    When I run "kanbus now kanbus-lazy-quiet-epic --no-recursive --list"
    Then the command should succeed
    And issue "kanbus-lazy-quiet-epic" should have right now summary "Quiet epic summary."
    And the LLM usage log should not contain a right_now_summary entry

  Scenario: Regenerating a right now summary updates a newer overlay snapshot
    Given an issue "kanbus-overlay-rn" exists with title "Overlay target"
    And a newer overlay snapshot for "kanbus-overlay-rn" has no right now summary
    When I update issue "kanbus-overlay-rn" to status "in_progress"
    Then the command should succeed
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should not contain "(no right-now summary)"
    And issue "kanbus-overlay-rn" should have a non-empty right now summary
