Feature: Structured outcomes from the Codex router adapter
  As an operator
  I want Codex results to use a versioned structured contract
  So that the router can own issue transitions and publication deterministically

  Background:
    Given a Kanbus project with valid Codex-first router configuration
    And package "kbs-401" has current claim "claim-401" at logical revision 1

  Scenario: The Codex adapter returns a completed result with checkpoint and artifacts
    Given the Codex adapter returns this result:
      """
      {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "Added input validation and tests.",
        "issue_updates": [],
        "checkpoint": {
          "ref": "refs/kanbus/router/checkpoints/kbs-401",
          "revision": 1
        },
        "artifacts": [
          {"name": "test-report", "ref": "refs/kanbus/router/artifacts/kbs-401/test-report-r1"}
        ]
      }
      """
    When I run "kanbus router run --once"
    Then package "kbs-401" should transition to status "review"
    And the router should publish the checkpoint and artifact references
    And the router should create a pull request for package "kbs-401"

  Scenario Outline: The Codex adapter tolerates a quoted schema version
    Given the Codex adapter returns this result:
      """
      {
        "schema_version": <version>,
        "outcome": "completed",
        "summary": "Removed the unused status.",
        "issue_updates": [],
        "checkpoint": null,
        "artifacts": []
      }
      """
    When I run "kanbus router run --once"
    Then package "kbs-401" should transition to status "review"

    Examples:
      | version |
      | "1"     |
      | "1.0"   |
      | 1.0     |

  Scenario Outline: The Codex adapter accepts only defined outcomes and preserves the turn for review
    Given the Codex adapter returns result outcome "<outcome>"
    When I run "kanbus router run --once"
    Then the command should fail with exit code 1
    And stderr should equal "error: invalid Codex router outcome \"<outcome>\"\n"
    And package "kbs-401" should transition to status "review"
    And package "kbs-401" should have a "Kanbus Issue Router" comment containing "Router detail: invalid Codex router outcome"

    Examples:
      | outcome        |
      | done           |
      | requested      |
      | failed         |
      | cancelled      |

  Scenario: Malformed Codex JSON is preserved for review
    Given the Codex adapter writes malformed JSON to standard output
    When I run "kanbus router run --once"
    Then the command should fail with exit code 1
    And stderr should equal "error: Codex router adapter returned invalid JSON\n"
    And package "kbs-401" should transition to status "review"
    And package "kbs-401" should have a "Kanbus Issue Router" comment containing "Router detail: Codex router adapter returned invalid JSON"

  Scenario: An agent that cannot start blocks the package with a router comment
    Given a fake forge is available for the router
    And provider profile "codex-default" has command "/nonexistent/agent-cli" and arguments []
    When I run "kanbus router run --once"
    Then the command should fail with exit code 1
    And package "kbs-401" should transition to status "blocked"
    And package "kbs-401" should have a "Kanbus Issue Router" comment containing "The router could not start an agent session"

  Scenario Outline: An agent that changes Kanbus project state is preserved for review with the reason
    Given the Codex adapter returns this result:
      """
      {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "Removed the unused status.",
        "issue_updates": [],
        "checkpoint": null,
        "artifacts": []
      }
      """
    And the Codex adapter <edit> Kanbus project state in its worktree
    When I run "kanbus router run --once"
    Then the command should fail with exit code 1
    And stderr should equal "error: router adapter may not modify Kanbus project state directly\n"
    And package "kbs-401" should transition to status "review"
    And package "kbs-401" should have a "Kanbus Issue Router" comment containing "Router detail: router adapter may not modify Kanbus project state directly"

    Examples:
      | edit               |
      | edits              |
      | edits and commits  |

  Scenario: An agent that only refreshes the derived project cache is not rejected
    Given the Codex adapter returns this result:
      """
      {
        "schema_version": 1,
        "outcome": "completed",
        "summary": "Removed the unused status.",
        "issue_updates": [],
        "checkpoint": null,
        "artifacts": []
      }
      """
    And the Codex adapter refreshes the project cache in its worktree
    When I run "kanbus router run --once"
    Then package "kbs-401" should transition to status "review"

  Scenario: A Codex issue update must remain inside the current package and workflow
    Given the Codex adapter returns issue update "kbs-999" to status "closed"
    When I run "kanbus router run --once"
    Then the command should fail with exit code 1
    And stderr should equal "error: issue kbs-999 is outside router package kbs-401\n"
    And package "kbs-401" should transition to status "review"

  Scenario: The Codex adapter receives a bounded package and the latest accepted checkpoint
    Given package "kbs-401" contains issues "kbs-401, kbs-402"
    And package "kbs-401" has accepted checkpoint "refs/kanbus/router/checkpoints/kbs-401" at revision 2
    When the Codex adapter starts claim "claim-401"
    Then the adapter request should include only issues "kbs-401, kbs-402"
    And the adapter request should include checkpoint "refs/kanbus/router/checkpoints/kbs-401" at revision 2
    And the adapter request should include claim "claim-401" at logical revision 3
