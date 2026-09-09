@wip
Feature: Standup CLI command
  As a Kanbus user
  I want to generate on-demand standup reports from the terminal
  So that I can prepare for meetings without manual synthesis

  Default invocation (no issue identifiers) uses the standup default fact feed:
  congregation-scoped (current project plus configured virtual_projects),
  `in_progress` OR `blocked`, capped at 30, ordered by updated_at descending.
  This widens `kanbus now`'s in_progress-only default for report usefulness.

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"

  Scenario: Standup without issue IDs succeeds with standup default selection
    Given an issue "kanbus-cli-def" exists with status "in_progress"
    And issue "kanbus-cli-def" has right now summary "CLI default scope work."
    When I run "kanbus standup"
    Then the command should succeed
    And the standup fact feed should match standup default listing

  Scenario: Omit-IDs includes blocked issues in fact feed and Blockers for meeting-script
    Given an issue "kanbus-cli-blk" exists with status "blocked"
    And issue "kanbus-cli-blk" has right now summary "Blocked on deploy approval."
    When I run "kanbus standup --profile meeting-script"
    Then the command should succeed
    And the standup fact feed should include issue "kanbus-cli-blk"
    And the standup report section "Blockers" should mention "kanbus-cli-blk"
    And the standup report section "Blockers" should mention "deploy approval"

  Scenario: Omit-IDs includes blocked issues in fact feed and Blockers for director-brief
    Given an issue "kanbus-cli-dblk" exists with status "blocked"
    And issue "kanbus-cli-dblk" has right now summary "Blocked on vendor response."
    When I run "kanbus standup --profile director-brief"
    Then the command should succeed
    And the standup fact feed should include issue "kanbus-cli-dblk"
    And the standup report section "Blockers" should mention "kanbus-cli-dblk"
    And the standup report section "Health" should report 1 blocked issue

  Scenario: Omit-IDs excludes open and backlog from the fact feed
    Given an issue "kanbus-cli-ip" exists with status "in_progress"
    And an issue "kanbus-cli-open" exists with status "open"
    And an issue "kanbus-cli-bl" exists with status "backlog"
    When I run "kanbus standup"
    Then the command should succeed
    And the standup fact feed should include issue "kanbus-cli-ip"
    And the standup fact feed should not include issue "kanbus-cli-open"
    And the standup fact feed should not include issue "kanbus-cli-bl"

  Scenario: Director brief without issue IDs succeeds board-wide
    Given an issue "kanbus-cli-brief" exists with status "in_progress"
    And issue "kanbus-cli-brief" has right now summary "Board-wide director brief."
    When I run "kanbus standup --profile director-brief"
    Then the command should succeed
    And the standup fact feed should match standup default listing

  Scenario: Standup rejects a missing issue identifier when scoped
    When I run "kanbus standup kanbus-stu-missing"
    Then the command should fail
    And stderr should contain "not found"

  Scenario: Standup supports multiple issue identifiers
    Given an issue "kanbus-cli-a" exists with status "in_progress"
    And issue "kanbus-cli-a" has right now summary "Alpha CLI work."
    And an issue "kanbus-cli-b" exists with status "in_progress"
    And issue "kanbus-cli-b" has right now summary "Beta CLI work."
    When I run "kanbus standup kanbus-cli-a kanbus-cli-b"
    Then the command should succeed
    And stdout should contain "Alpha CLI work."
    And stdout should contain "Beta CLI work."

  Scenario: Standup no-recursive limits scope to selected issues
    Given an issue "kanbus-cli-init" of type "initiative" with status "open" and parent "kanbus-cli-missing" and title "CLI initiative"
    And an issue "kanbus-cli-child" of type "task" with status "in_progress" and parent "kanbus-cli-init" and title "CLI child"
    And issue "kanbus-cli-child" has right now summary "Child-only work."
    When I run "kanbus standup kanbus-cli-init --no-recursive"
    Then the command should succeed
    And stdout should not contain "Child-only work."

  Scenario: Standup no-recursive requires issue identifiers
    When I run "kanbus standup --no-recursive"
    Then the command should fail
    And stderr should contain "--no-recursive requires one or more issue identifiers"

  Scenario: Standup rejects unknown profile names
    Given an issue "kanbus-cli-prof" exists with title "Profile test"
    When I run "kanbus standup kanbus-cli-prof --profile not-a-profile"
    Then the command should fail
    And stderr should contain "unknown standup profile"
