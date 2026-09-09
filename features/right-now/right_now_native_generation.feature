Feature: Right now native in-runtime generation
  As a Kanbus user on a single-runtime install
  I want right-now summaries generated in-process by the active CLI
  So that standup and JIT backfill never shell out to a missing subcommand

  Background:
    Given a Kanbus project with default configuration
    And mock AI is disabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: JIT backfill uses native LiteLLM without kanbus self-delegation
    Given right now native litellm test completion is "Shipped via native runtime."
    And an issue "kanbus-native1" exists with title "Native path issue"
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And issue "kanbus-native1" should have right now summary "Shipped via native runtime."
    And stderr should not contain "now-generate-internal"
    And stderr should not contain "unrecognized subcommand"

  Scenario: Persisted mock summaries regenerate through native LiteLLM
    Given right now native litellm test completion is "Regenerated via native runtime."
    And an issue "kanbus-native2" exists with title "Mock persisted native issue"
    And issue "kanbus-native2" has right now summary "Mock right-now summary for kanbus-native2."
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should contain "Regenerated via native runtime."
    And stdout should not contain "Mock right-now summary for kanbus-native2."
    And issue "kanbus-native2" should have right now summary "Regenerated via native runtime."
    And stderr should not contain "now-generate-internal"
