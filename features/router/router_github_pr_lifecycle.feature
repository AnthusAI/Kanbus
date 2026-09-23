Feature: GitHub pull request lifecycle for routed packages
  As an operator
  I want pull request activity reconciled back to Kanbus
  So that review and merge, rather than agent completion, determine package completion

  Background:
    Given a Kanbus project with valid Codex-first router configuration
    And GitHub is the configured forge for repository "anthusai/kanbus"

  Scenario: A completed Codex run opens a pull request and moves the package to review
    Given package "kbs-501" completes at logical revision 4 on branch "codex/router/kbs-501/r4"
    When the router publishes the completed result
    Then the router should open a pull request with title "[kbs-501] Implement router planning"
    And the pull request should use head branch "codex/router/kbs-501/r4"
    And the pull request should use base branch "main"
    And the pull request body should include "Kanbus package: kbs-501"
    And package "kbs-501" should transition to status "review"

  Scenario: Opening and synchronizing a pull request keep the package in review
    Given package "kbs-502" has router pull request 52 at head "abc123"
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-1",
        "kind": "pull_request",
        "action": "opened",
        "repository": "anthusai/kanbus",
        "number": 52,
        "head_sha": "abc123",
        "merged": false
      }
      """
    And GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-2",
        "kind": "pull_request",
        "action": "synchronize",
        "repository": "anthusai/kanbus",
        "number": 52,
        "head_sha": "def456",
        "merged": false
      }
      """
    Then package "kbs-502" should remain in status "review"
    And GitHub event IDs "evt-1, evt-2" should be recorded once each

  Scenario: A requested-changes review requeues the package ahead of pending work
    Given package "kbs-503" is in status "review" with pull request 53 at head "abc503"
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-3",
        "kind": "pull_request",
        "action": "requested_changes",
        "repository": "anthusai/kanbus",
        "number": 53,
        "head_sha": "abc503",
        "merged": false
      }
      """
    Then package "kbs-503" should transition to status "in_progress"
    And package "kbs-503" should be ordered before pending package "kbs-504"
    And the next run should continue on pull request 53

  Scenario: Approval alone does not complete a package
    Given package "kbs-505" is in status "review" with pull request 55 at head "abc505"
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-4",
        "kind": "pull_request",
        "action": "approved",
        "repository": "anthusai/kanbus",
        "number": 55,
        "head_sha": "abc505",
        "merged": false
      }
      """
    Then package "kbs-505" should remain in status "review"
    And package "kbs-505" should have approval recorded for head "abc505"

  Scenario: A new commit invalidates approval for the previous pull request head
    Given package "kbs-510" is in status "review" with pull request 60 at head "abc510"
    And pull request 60 has an approval recorded for head "abc510"
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-10",
        "kind": "pull_request",
        "action": "synchronize",
        "repository": "anthusai/kanbus",
        "number": 60,
        "head_sha": "def510",
        "merged": false
      }
      """
    Then package "kbs-510" should remain in status "review"
    And pull request 60 should not have approval for head "def510"

  Scenario Outline: GitHub check runs update the review lifecycle
    Given package "kbs-511" is in status "review" with pull request 61 at head "abc511"
    When GitHub sends router check-run event "evt-<event>" for pull request 61 and head "abc511" with conclusion "<conclusion>"
    Then package "kbs-511" should <expected> after the check-run event

    Examples:
      | event | conclusion | expected         |
      | pass  | success    | remain in review |
      | fail  | failure    | return to active |

  Scenario: A merged approved pull request moves the package to terminal status
    Given package "kbs-506" is in status "review" with pull request 56 at head "abc506"
    And pull request 56 has an approval recorded for head "abc506"
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-5",
        "kind": "pull_request",
        "action": "closed",
        "repository": "anthusai/kanbus",
        "number": 56,
        "head_sha": "abc506",
        "merged": true
      }
      """
    Then package "kbs-506" should transition to terminal status "closed"

  Scenario: Merge without approval does not complete a package
    Given package "kbs-507" is in status "review" with pull request 57 at head "abc507"
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-6",
        "kind": "pull_request",
        "action": "closed",
        "repository": "anthusai/kanbus",
        "number": 57,
        "head_sha": "abc507",
        "merged": true
      }
      """
    Then package "kbs-507" should remain in status "review"
    And the router should record diagnostic "merged pull request has no approval for its current head"

  Scenario: Closing a pull request without merge blocks the package
    Given package "kbs-508" is in status "review" with pull request 58 at head "abc508"
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-7",
        "kind": "pull_request",
        "action": "closed",
        "repository": "anthusai/kanbus",
        "number": 58,
        "head_sha": "abc508",
        "merged": false
      }
      """
    Then package "kbs-508" should transition to status "blocked"

  Scenario: Duplicate forge event IDs are idempotent
    Given package "kbs-509" is in status "review" with pull request 59 at head "abc509"
    When the router receives the same approved GitHub event "evt-8" twice for pull request 59 and head "abc509"
    Then one approval event should be recorded
    And package "kbs-509" should remain in status "review"

  Scenario: Events for an unknown pull request or a mismatched head are rejected
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-9",
        "kind": "pull_request",
        "action": "requested_changes",
        "repository": "anthusai/kanbus",
        "number": 999,
        "head_sha": "unknown",
        "merged": false
      }
      """
    Then the event should fail with exit code 1
    And stderr should equal "error: GitHub pull request 999 is not owned by the Issue Router\n"

  Scenario: A GitHub event for another repository is rejected
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-11",
        "kind": "pull_request",
        "action": "opened",
        "repository": "other/project",
        "number": 11,
        "head_sha": "abc11",
        "merged": false
      }
      """
    Then the event should fail with exit code 1
    And stderr should equal "error: GitHub event repository \"other/project\" does not match configured repository \"anthusai/kanbus\"\n"
