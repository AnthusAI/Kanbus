Feature: Manage AGENTS.md Kanbus instructions
  As a Kanbus user
  I want a command that ensures AGENTS.md contains Kanbus guidance
  So that task management requirements are enforced consistently

  Scenario: Create AGENTS.md when missing
    Given a Kanbus repository without AGENTS.md
    When I run "kanbus setup agents"
    Then AGENTS.md should exist
    And AGENTS.md should contain the Kanbus section
    And CONTRIBUTING_AGENT.md should exist
    And CONTRIBUTING_AGENT.md should contain "This is The Way."
    And CONTRIBUTING_AGENT.md should contain "As a <role>, I want <capability>, so that <benefit>."

  Scenario: Insert Kanbus section after H1 when missing
    Given a Kanbus repository with AGENTS.md without a Kanbus section
    When I run "kanbus setup agents"
    Then AGENTS.md should contain the Kanbus section
    And the Kanbus section should appear after the H1 heading
    And CONTRIBUTING_AGENT.md should exist

  Scenario: Prompt and decline overwrite
    Given a Kanbus repository with AGENTS.md containing a Kanbus section
    When I run "kanbus setup agents" and respond "n"
    Then AGENTS.md should be unchanged
    And CONTRIBUTING_AGENT.md should exist

  Scenario: Prompt and accept overwrite
    Given a Kanbus repository with AGENTS.md containing a Kanbus section
    When I run "kanbus setup agents" and respond "y"
    Then AGENTS.md should contain the Kanbus section
    And CONTRIBUTING_AGENT.md should exist

  Scenario: Non-interactive overwrite requires force
    Given a Kanbus repository with AGENTS.md containing a Kanbus section
    When I run "kanbus setup agents" non-interactively
    Then the command should fail
    And stderr should contain "Kanbus section already exists in AGENTS.md. Re-run with --force to overwrite."

  Scenario: Force overwrite without prompt
    Given a Kanbus repository with AGENTS.md containing a Kanbus section
    When I run "kanbus setup agents --force"
    Then AGENTS.md should contain the Kanbus section
    And CONTRIBUTING_AGENT.md should exist
