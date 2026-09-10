Feature: Agent provenance guidance
  As a coding agent using Kanbus
  I want incomplete provenance to warn with a ready follow-up command
  So that I can tag the same issue or comment in one step if I choose

  Scenario: Create without provenance succeeds and warns with an update command
    Given a Kanbus project with default configuration
    When I run "kanbus create \"Untagged task\" --type task"
    Then the command should succeed
    And the created issue should not have agent metadata
    And stderr should contain "agent provenance is incomplete"
    And stderr should contain "CONTRIBUTING_AGENT.md"
    And stderr should contain "kbs update"
    And stderr should contain "--agent-platform \"Cursor\""
    And stderr should contain "--agent-model \"Composer 2.5\""
    And stderr should contain "--agent-name \"Cloud Agent\""
    And stderr should contain "--no-agent-provenance"

  Scenario: Comment without provenance succeeds and warns with a comment update command
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    When I run "kanbus comment kanbus-aaa \"Note\""
    Then the command should succeed
    And stderr should contain "agent provenance is incomplete"
    And stderr should contain "kbs comment update"
    And stderr should contain "--agent-platform \"Cursor\""
    And stderr should contain "--agent-name \"Cloud Agent\""

  Scenario: Override silences the provenance warning
    Given a Kanbus project with default configuration
    When I run "kanbus create \"Human note\" --type task --no-agent-provenance"
    Then the command should succeed
    And stderr should not contain "agent provenance is incomplete"

  Scenario: Complete provenance does not warn
    Given a Kanbus project with default configuration
    When I run "kanbus create \"Tagged\" --type task --agent-platform Cursor --agent-model \"Composer 2.5\" --agent-name \"Cloud Agent\""
    Then the command should succeed
    And stderr should not contain "agent provenance is incomplete"

  Scenario: Update sets issue agent when it was absent
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    When I run "kanbus update kanbus-aaa --agent-platform Cursor --agent-model \"Composer 2.5\" --agent-name \"Cloud Agent\""
    Then the command should succeed
    And issue "kanbus-aaa" should have agent metadata platform "cursor" and model "Composer 2.5"
    And issue "kanbus-aaa" should have agent name "Cloud Agent"

  Scenario: Comment update sets comment agent without changing text
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And issue "kanbus-aaa" has a comment from "agent" with text "Done" and id "abc123def456"
    When I run "kanbus comment update kanbus-aaa abc123def456 --agent-platform Cursor --agent-model \"Composer 2.5\" --agent-name \"Cloud Agent\""
    Then the command should succeed
    And the latest comment should have agent platform "cursor" and model "Composer 2.5"
    And the latest comment should have text "Done"

  Scenario: Update rejects replacing complete agent metadata
    Given a Kanbus project with default configuration
    And an issue "kanbus-agent" exists with agent metadata platform "cursor" model "Composer 2.5" and name "Cloud Agent"
    When I run "kanbus update kanbus-agent --agent-platform Codex --agent-model \"GPT-5\" --agent-name \"Other Agent\""
    Then the command should fail with exit code 1
    And stderr should contain "agent metadata is already set"

  Scenario: Create help mentions provenance guidance
    Given a Kanbus project with default configuration
    When I run "kanbus create --help"
    Then the command should succeed
    And stdout should contain "agent-platform"
    And stdout should contain "CONTRIBUTING_AGENT.md"
