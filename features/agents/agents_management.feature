Feature: Manage AGENTS.md Taskulus instructions
  As a Taskulus user
  I want a command that ensures AGENTS.md contains Taskulus guidance
  So that task management requirements are enforced consistently

  Scenario: Create AGENTS.md when missing
    Given a Taskulus repository without AGENTS.md
    When I run "tsk setup agents"
    Then AGENTS.md should exist
    And AGENTS.md should contain the Taskulus section
    And CONTRIBUTING_AGENT.md should exist
    And CONTRIBUTING_AGENT.md should contain "This is The Way."
    And CONTRIBUTING_AGENT.md should contain "As a <role>, I want <capability>, so that <benefit>."

  Scenario: Insert Taskulus section after H1 when missing
    Given a Taskulus repository with AGENTS.md without a Taskulus section
    When I run "tsk setup agents"
    Then AGENTS.md should contain the Taskulus section
    And the Taskulus section should appear after the H1 heading
    And CONTRIBUTING_AGENT.md should exist

  Scenario: Prompt and decline overwrite
    Given a Taskulus repository with AGENTS.md containing a Taskulus section
    When I run "tsk setup agents" and respond "n"
    Then AGENTS.md should be unchanged
    And CONTRIBUTING_AGENT.md should exist

  Scenario: Prompt and accept overwrite
    Given a Taskulus repository with AGENTS.md containing a Taskulus section
    When I run "tsk setup agents" and respond "y"
    Then AGENTS.md should contain the Taskulus section
    And CONTRIBUTING_AGENT.md should exist

  Scenario: Non-interactive overwrite requires force
    Given a Taskulus repository with AGENTS.md containing a Taskulus section
    When I run "tsk setup agents" non-interactively
    Then the command should fail
    And stderr should contain "Taskulus section already exists in AGENTS.md. Re-run with --force to overwrite."

  Scenario: Force overwrite without prompt
    Given a Taskulus repository with AGENTS.md containing a Taskulus section
    When I run "tsk setup agents --force"
    Then AGENTS.md should contain the Taskulus section
    And CONTRIBUTING_AGENT.md should exist
