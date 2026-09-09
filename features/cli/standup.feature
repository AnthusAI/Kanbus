@wip
Feature: Standup CLI command
  As a Kanbus user
  I want to generate on-demand standup reports from the terminal
  So that I can prepare for meetings without manual synthesis

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Standup requires at least one issue identifier
    When I run "kanbus standup"
    Then the command should fail
    And stderr should contain "requires one or more issue identifiers"

  Scenario: Standup rejects a missing issue identifier
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
