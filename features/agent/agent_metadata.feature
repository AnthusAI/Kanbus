Feature: Agent metadata on issues and comments
  As an AI agent using Kanbus
  I want to optionally tag mutations with platform and model info
  So that provenance is preserved without cluttering default output

  Scenario: Create issue with agent metadata via flags
    Given a Kanbus project with default configuration
    And the current user is "agent"
    When I run "kanbus create \"Agent task\" --type task --agent-platform cursor --agent-model composer-2.5"
    Then the command should succeed
    And the created issue should have agent metadata platform "cursor" and model "composer-2.5"
    And stdout should contain "Agent: cursor / composer-2.5"

  Scenario: Create issue without agent metadata omits Agent row
    Given a Kanbus project with default configuration
    When I run "kanbus create \"Plain task\" --type task"
    Then the command should succeed
    And stdout should not contain "Agent:"

  Scenario: Comment with agent metadata from environment variables
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And the current user is "agent"
    And KANBUS_AGENT_PLATFORM is set to "cursor"
    And KANBUS_AGENT_MODEL is set to "composer-2.5"
    When I run "kanbus comment kanbus-aaa \"Progress note\""
    Then the command should succeed
    And the latest comment should have agent platform "cursor" and model "composer-2.5"

  Scenario: CLI flags override agent environment variables
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And KANBUS_AGENT_PLATFORM is set to "cursor"
    And KANBUS_AGENT_MODEL is set to "composer-2.5"
    When I run "kanbus comment kanbus-aaa \"Override note\" --agent-platform codex --agent-model gpt-5"
    Then the latest comment should have agent platform "codex" and model "gpt-5"

  Scenario: Invalid agent settings JSON fails
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    When I run "kanbus comment kanbus-aaa \"Bad settings\" --agent-platform cursor --agent-model x --agent-settings not-json"
    Then the command should fail with exit code 1
    And stderr should contain "invalid agent settings"

  Scenario: Show JSON includes agent metadata when present
    Given a Kanbus project with default configuration
    And an issue "kanbus-agent" exists with agent metadata platform "cursor" and model "composer-2.5"
    When I run "kanbus show kanbus-agent --json"
    Then the command should succeed
    And stdout should contain "\"agent\""
    And stdout should contain "\"platform\": \"cursor\""
    And stdout should contain "\"model\": \"composer-2.5\""

  Scenario: Format issue display includes agent metadata on issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-agent" exists with agent metadata platform "cursor" and model "composer-2.5"
    When I format issue "kanbus-agent" for display
    Then the formatted output should contain text "Agent: cursor / composer-2.5"

  Scenario: Format issue display includes agent metadata on comments
    Given a Kanbus project with default configuration
    And an issue "kanbus-commented" exists
    And issue "kanbus-commented" has a comment from "agent" with text "Done" and agent metadata platform "cursor" and model "composer-2.5"
    When I format issue "kanbus-commented" for display
    Then the formatted output should contain text "agent (cursor / composer-2.5):"
    And the formatted output should contain text "Done"

  Scenario: Beads mode rejects agent flags on create
    Given a Kanbus project with beads compatibility enabled
    When I run "kanbus create \"Task\" --type task --agent-platform cursor --agent-model x"
    Then the command should fail with exit code 1
    And stderr should contain "agent metadata requires native Kanbus issue storage"

  Scenario: Beads mode rejects agent flags on comment
    Given a Kanbus project with beads compatibility enabled
    And an issue "kanbus-aaa" exists
    When I run "kanbus comment kanbus-aaa \"Note\" --agent-platform cursor --agent-model x"
    Then the command should fail with exit code 1
    And stderr should contain "agent metadata requires native Kanbus issue storage"
