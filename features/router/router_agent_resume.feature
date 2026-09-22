Feature: Resuming an agent's saved session with a human reply
  As an operator
  I want a human's reply to a blocked agent to continue the same agent session
  So that the agent keeps its context and its unfinished work instead of starting over

  Background:
    Given a Kanbus project with valid Codex-first router configuration
    And a fake forge is available for the router

  Scenario: A human reply resumes the saved session instead of starting a new one
    Given package "kbs-401" asked a question in session "session-A" on branch "codex/router/kbs-401/r1"
    And a human replied "Use option B." to package "kbs-401"
    And package "kbs-401" is ready again
    And the Codex adapter returns this result:
      """
      {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "Applied option B.",
        "issue_updates": [],
        "checkpoint": null,
        "artifacts": []
      }
      """
    When I run "kanbus router run --once"
    Then the adapter should resume session "session-A" with a prompt containing "Use option B."
    And no new agent session should have been started for package "kbs-401"
    And package "kbs-401" should transition to status "review"

  Scenario: The resumed run continues on the branch the agent already worked on
    Given package "kbs-401" asked a question in session "session-A" on branch "codex/router/kbs-401/r1"
    And a human replied "Use option B." to package "kbs-401"
    And package "kbs-401" is ready again
    And the Codex adapter returns this result:
      """
      {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "Applied option B.",
        "issue_updates": [],
        "checkpoint": null,
        "artifacts": []
      }
      """
    When I run "kanbus router run --once"
    Then the run should use branch "codex/router/kbs-401/r1"

  Scenario: A ready package with no saved session starts a fresh session
    Given package "kbs-401" is ready and has never been run
    And the Codex adapter returns this result:
      """
      {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "Done.",
        "issue_updates": [],
        "checkpoint": null,
        "artifacts": []
      }
      """
    When I run "kanbus router run --once"
    Then the adapter should start a fresh session for package "kbs-401"
    And package "kbs-401" should transition to status "review"

  Scenario: Moving a question back to ready without a reply starts a fresh session
    Given package "kbs-401" asked a question in session "session-A" on branch "codex/router/kbs-401/r1"
    And package "kbs-401" is ready again
    And the Codex adapter returns this result:
      """
      {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "Done.",
        "issue_updates": [],
        "checkpoint": null,
        "artifacts": []
      }
      """
    When I run "kanbus router run --once"
    Then the adapter should start a fresh session for package "kbs-401"

  Scenario: A reply written before the question is not replayed
    Given a human replied "Old advice." to package "kbs-401"
    And package "kbs-401" asked a question in session "session-A" on branch "codex/router/kbs-401/r1"
    And package "kbs-401" is ready again
    And the Codex adapter returns this result:
      """
      {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "Done.",
        "issue_updates": [],
        "checkpoint": null,
        "artifacts": []
      }
      """
    When I run "kanbus router run --once"
    Then the adapter should start a fresh session for package "kbs-401"
