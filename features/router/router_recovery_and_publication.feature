Feature: Issue Router retries, checkpoints, and fenced publication
  As an operator
  I want retries and results to be fenced by the current claim revision
  So that stale work cannot replace an accepted checkpoint or publish a result

  Background:
    Given a Kanbus project with valid Codex-first router configuration
    And the maximum retry attempts are 3

  Scenario: A retryable failure preserves the checkpoint and schedules bounded backoff
    Given active package "kbs-301" has accepted checkpoint "refs/kanbus/router/checkpoints/kbs-301" at revision 4
    And the fake adapter returns outcome "retryable_failure" for attempt 1
    When I run "kanbus router run --once"
    Then the command should fail with exit code 1
    And package "kbs-301" should remain in status "in_progress"
    And package "kbs-301" should have attempt 2 available after 30 seconds
    And the next attempt should start from checkpoint "refs/kanbus/router/checkpoints/kbs-301" at revision 4
    And stdout should equal "Issue Router run completed: started=1 completed=0 review=0 failed=1 deferred=0\n"

  Scenario Outline: Retry delay doubles and is capped at fifteen minutes
    Given router retry max attempts is 8
    And package "kbs-302" has failed retryably <attempt> times
    When I inspect its next retry time
    Then the retry delay should be <delay>

    Examples:
      | attempt | delay  |
      | 1       | 30s    |
      | 2       | 60s    |
      | 3       | 120s   |
      | 6       | 900s   |
      | 7       | 900s   |

  Scenario: The third retryable failure moves the package to the configured blocked status
    Given package "kbs-303" is active at attempt 3
    And the fake adapter returns outcome "retryable_failure"
    When I run "kanbus router run --once"
    Then package "kbs-303" should transition to status "blocked"
    And package "kbs-303" should record the diagnostic "maximum retry attempts reached"
    And the accepted checkpoint should remain available for a human or later router run

  Scenario: An adapter blocked outcome moves the package to blocked without retry
    Given active package "kbs-304" is at attempt 1
    And the fake adapter returns outcome "blocked"
    When I run "kanbus router run --once"
    Then package "kbs-304" should transition to status "blocked"
    And package "kbs-304" should not receive a retry time

  Scenario: An agent that cannot be launched leaves a visible diagnostic and blocks the package
    Given active package "kbs-305" is at attempt 1
    And provider profile "codex-default" uses a command that does not exist
    And the router forge is not configured
    When I run "kanbus router run --once"
    Then the command should fail with exit code 1
    And package "kbs-305" should transition to status "blocked"
    And package "kbs-305" should have a router comment starting with "The router could not start an agent session:"

  Scenario: A current claim may publish its checkpoint and artifact references
    Given package "kbs-310" has current claim "claim-current" at logical revision 5
    When claim "claim-current" publishes result:
      """
      {
        "schema_version": 1,
        "package_id": "kbs-310",
        "claim_id": "claim-current",
        "revision": 5,
        "outcome": "completed",
        "summary": "Implementation is ready for review.",
        "checkpoint": {
          "ref": "refs/kanbus/router/checkpoints/kbs-310",
          "revision": 5
        },
        "artifacts": [
          {"name": "test-report", "ref": "refs/kanbus/router/artifacts/kbs-310/test-report-r5"}
        ],
        "issue_updates": []
      }
      """
    Then the result should be accepted
    And the accepted checkpoint should be "refs/kanbus/router/checkpoints/kbs-310" at revision 5
    And artifact "test-report" should be published as "refs/kanbus/router/artifacts/kbs-310/test-report-r5"

  Scenario: An obsolete claim cannot publish a checkpoint, artifact, or result
    Given package "kbs-311" has current claim "claim-new" at logical revision 7
    And package "kbs-311" has obsolete claim "claim-old" at logical revision 6
    When claim "claim-old" publishes a completed result with checkpoint "refs/kanbus/router/checkpoints/kbs-311" and artifact "refs/kanbus/router/artifacts/kbs-311/stale"
    Then the publication should fail with exit code 1
    And stderr should equal "error: stale router claim claim-old for package kbs-311; current claim is claim-new at revision 7\n"
    And the accepted checkpoint should not change
    And no artifact reference from claim "claim-old" should be published

  Scenario: A result for an older logical revision is rejected even when its claim ID matches
    Given package "kbs-312" has current claim "claim-current" at logical revision 8
    When claim "claim-current" publishes a result at logical revision 7
    Then the publication should fail with exit code 1
    And stderr should equal "error: stale router revision 7 for package kbs-312; current revision is 8\n"

  Scenario: An adapter cannot update an issue outside its routed package
    Given package "kbs-313" contains issues "kbs-313, kbs-314"
    And package "kbs-313" has current claim "claim-current" at logical revision 1
    When claim "claim-current" publishes issue update "kbs-999" to status "closed"
    Then the publication should fail with exit code 1
    And stderr should equal "error: issue kbs-999 is outside router package kbs-313\n"
    And no issue status should change

  Scenario: An adapter cannot publish an issue transition outside its workflow
    Given package "kbs-315" has current claim "claim-current" at logical revision 1
    When claim "claim-current" publishes issue update "kbs-315" to status "closed"
    Then the publication should fail with exit code 1
    And stderr should equal "error: router result cannot transition package kbs-315 from in_progress to closed\n"
    And no issue status should change

  Scenario: Human comments and empty heartbeats do not renew stale ownership
    Given package "kbs-316" has current claim "claim-current" with no progress for 24 hours
    When a human adds a comment to issue "kbs-316"
    And the adapter sends an empty heartbeat for claim "claim-current"
    Then the stale ownership age should remain 24 hours
    And the package should be eligible for takeover

  Scenario: Structured progress and accepted checkpoints renew stale ownership
    Given package "kbs-317" has current claim "claim-current" with no progress for 23 hours
    When claim "claim-current" publishes structured progress at the current revision
    Then the stale ownership age should reset to zero
    When claim "claim-current" publishes an accepted checkpoint at the current revision
    Then the stale ownership age should remain zero
