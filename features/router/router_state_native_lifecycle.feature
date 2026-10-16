Feature: State-native Issue Router lifecycle
  As an operator
  I want the Issue Router to drive work through the statuses my project marks as router statuses
  So that dispatch, review, and completion follow the board instead of a duplicate status map

  Background:
    Given a Kanbus project with valid Codex-first router configuration
    And the project has the canonical router statuses

  Scenario: An opted-in issue in the marked todo status is selected for dispatch
    Given the issue hierarchy and labels are:
      | issue_id | parent | status    | labels                     |
      | kbs-401  |        | Discovery | agent-class:implementation |
    When I run "kanbus router plan --json"
    Then issue "kbs-401" should appear in the eligible packages

  Scenario: A claimed issue moves directly from the marked todo status to the marked in-progress status
    Given pending routed packages are ordered "kbs-402"
    And provider profile "codex-default" runs fake adapter outcome "completed"
    When I run "kanbus router run --once"
    Then the command should succeed
    And package "kbs-402" should have transitioned from status "Discovery" to status "in_progress" when it was claimed

  Scenario: Successful agent work moves to the marked in-review status and stays there
    Given pending routed packages are ordered "kbs-403"
    And provider profile "codex-default" runs fake adapter outcome "completed"
    When I run "kanbus router run --once"
    Then the command should succeed
    And package "kbs-403" should be in status "review"
    And package "kbs-403" should not be in a status with semantic category "done"
    And the router should not close package "kbs-403"

  Scenario: A merged, approved pull request moves reviewed work to the marked done status
    Given GitHub is the configured forge for repository "anthusai/kanbus"
    And package "kbs-404" is in status "review" with pull request 64 at head "abc404"
    And pull request 64 has an approval recorded for head "abc404"
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-404",
        "kind": "pull_request",
        "action": "closed",
        "repository": "anthusai/kanbus",
        "number": 64,
        "head_sha": "abc404",
        "merged": true
      }
      """
    Then package "kbs-404" should transition to terminal status "closed"

  Scenario: Blocked and cancelled work moves to the marked blocked status
    Given active package "kbs-405" is at attempt 1
    And the fake adapter returns outcome "blocked"
    When I run "kanbus router run --once"
    Then package "kbs-405" should transition to status "blocked"

  Scenario: Requested changes return reviewed work to the marked in-progress status
    Given GitHub is the configured forge for repository "anthusai/kanbus"
    And package "kbs-406" is in status "review" with pull request 66 at head "abc406"
    When GitHub sends router event:
      """
      {
        "schema_version": 1,
        "event_id": "evt-406",
        "kind": "pull_request",
        "action": "requested_changes",
        "repository": "anthusai/kanbus",
        "number": 66,
        "head_sha": "abc406",
        "merged": false
      }
      """
    Then package "kbs-406" should transition to status "in_progress"

  Scenario Outline: An unmarked todo status is deferred as not router intake
    Given an issue "kbs-410" of type "task" with status "<status>" and label "agent-class:implementation"
    When I run "kanbus router plan --json"
    Then issue "kbs-410" should not appear in the eligible packages
    And issue "kbs-410" should be deferred with reason "status_not_router_intake"

    Examples:
      | status  |
      | open    |
      | backlog |

  Scenario: A todo status added by the project is deferred as not router intake unless it is marked
    Given the configuration adds the status "triage" with semantic category "todo"
    And an issue "kbs-411" of type "task" with status "triage" and label "agent-class:implementation"
    When I run "kanbus router plan --json"
    Then issue "kbs-411" should not appear in the eligible packages
    And issue "kbs-411" should be deferred with reason "status_not_router_intake"

  Scenario: A one-shot run leaves an eligible-looking Ready issue untouched
    Given an issue "kbs-412" of type "task" with status "open" and label "agent-class:implementation"
    And there are no eligible router packages
    When I run "kanbus router run --once"
    Then the command should succeed
    And no adapter should have run
    And package "kbs-412" should remain in status "open"

  Scenario: Unmarked statuses are never router transition targets
    Given active package "kbs-413" is at attempt 1
    And the fake adapter returns outcome "blocked"
    And the configuration adds the status "paused" with semantic category "blocked"
    When I run "kanbus router run --once"
    Then package "kbs-413" should transition to status "blocked"
    And package "kbs-413" should not transition to status "paused"

  Scenario: Unmarked statuses in a category do not consume router work-in-progress limits
    Given the configuration adds the status "paused" with semantic category "in_progress"
    And project WIP limit is 1
    And project issues in router WIP statuses are:
      | issue_id | status | labels                     | assignee |
      | kbs-414  | paused | agent-class:implementation |          |
    And pending routed packages are ordered "kbs-415"
    When I run "kanbus router plan --json"
    Then issue "kbs-415" should appear in the eligible packages

  Scenario: An adapter cannot publish a transition to an unmarked status
    Given package "kbs-420" has current claim "claim-current" at logical revision 1
    And the configuration adds the status "paused" with semantic category "in_progress"
    When claim "claim-current" publishes issue update "kbs-420" to status "paused"
    Then the publication should fail with exit code 1
    And stderr should equal "error: router result cannot transition package kbs-420 from in_progress to paused\n"
    And no issue status should change

  Scenario: Existing issues in an unmarked status are deferred and not migrated
    Given an issue "kbs-421" of type "task" with status "open" and label "agent-class:implementation"
    When I run "kanbus router plan --json"
    Then issue "kbs-421" should not appear in the eligible packages
    And issue "kbs-421" should be deferred with reason "status_not_router_intake"
    And issue "kbs-421" should remain in status "open"
