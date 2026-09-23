Feature: Deterministic Issue Router planning
  As an operator
  I want a stable plan of routed work and explicit capacity reasons
  So that the same board state produces the same dispatch decision

  Background:
    Given a Kanbus project with valid Codex-first router configuration

  Scenario: A package uses its root routing label and excludes a separately routed descendant
    Given the issue hierarchy and labels are:
      | issue_id | parent   | status | labels                         |
      | kbs-101  |          | open   | agent-class:implementation     |
      | kbs-102  | kbs-101  | open   |                                |
      | kbs-103  | kbs-102  | open   | agent-provider:codex-default   |
      | kbs-104  | kbs-103  | open   |                                |
    When I run "kanbus router plan --json"
    Then stdout should equal the following JSON value with 2-space indentation and a trailing newline:
      """
      {
        "version": 1,
        "enabled": true,
        "paused": false,
        "eligible": [
          {
            "issue_id": "kbs-101",
            "route": {
              "kind": "class",
              "name": "implementation",
              "provider_profile": "codex-default"
            },
            "package_issue_ids": ["kbs-101", "kbs-102"],
            "pending_since": "2026-09-17T10:00:00Z",
            "attempt": 1
          },
          {
            "issue_id": "kbs-103",
            "route": {
              "kind": "provider",
              "name": "codex-default",
              "provider_profile": "codex-default"
            },
            "package_issue_ids": ["kbs-103", "kbs-104"],
            "pending_since": "2026-09-17T10:00:00Z",
            "attempt": 1
          }
        ],
        "deferred": []
      }
      """

  Scenario: A human assignee remains unchanged and does not act as a routing label
    Given issue "kbs-110" is pending with assignee "alex@example.com" and no routing label
    When I run "kanbus router plan --json"
    Then issue "kbs-110" should not appear in the eligible packages
    And issue "kbs-110" should remain assigned to "alex@example.com"

  Scenario Outline: A package root must have exactly one routing label
    Given pending issue "kbs-120" has routing labels "<labels>"
    When I run "kanbus router plan --json"
    Then issue "kbs-120" should be deferred with reason "invalid_route"

    Examples:
      | labels                                                  |
      |                                                         |
      | agent-class:implementation agent-class:implementation  |
      | agent-class:implementation agent-provider:codex-default|
      | agent-class:unknown                                     |
      | agent-provider:unknown                                 |

  Scenario: A class route selects its first configured available provider profile
    Given class "implementation" is configured with provider profiles "codex-default, codex-backup"
    And provider profile "codex-default" has reached its WIP limit
    And pending issue "kbs-130" has routing label "agent-class:implementation"
    When I run "kanbus router plan --json"
    Then issue "kbs-130" should be eligible with provider profile "codex-backup"

  Scenario: A provider route remains pinned when that provider is at its WIP limit
    Given provider profile "codex-default" has reached its WIP limit
    And pending issue "kbs-131" has routing label "agent-provider:codex-default"
    When I run "kanbus router plan --json"
    Then issue "kbs-131" should be deferred with reason "provider_wip_limit"

  Scenario: Recoverable active and requested-change work precede pending work
    Given router candidates are:
      | issue_id | state             | pending_since          | created_at              |
      | kbs-141  | pending           | 2026-09-17T09:00:00Z   | 2026-09-16T08:00:00Z    |
      | kbs-142  | requested_changes | 2026-09-17T11:00:00Z   | 2026-09-16T09:00:00Z    |
      | kbs-143  | recoverable_active| 2026-09-17T12:00:00Z   | 2026-09-16T10:00:00Z    |
      | kbs-144  | pending           | 2026-09-17T09:00:00Z   | 2026-09-16T07:00:00Z    |
    When I run "kanbus router plan --json"
    Then eligible package order should be "kbs-143, kbs-142, kbs-144, kbs-141"

  Scenario: Pending work uses entered time, creation time, and issue ID as tie-breakers
    Given router candidates are:
      | issue_id | state   | pending_since          | created_at              |
      | kbs-152  | pending | 2026-09-17T09:00:00Z   | 2026-09-16T07:00:00Z    |
      | kbs-151  | pending | 2026-09-17T09:00:00Z   | 2026-09-16T07:00:00Z    |
      | kbs-150  | pending | 2026-09-17T08:00:00Z   | 2026-09-16T09:00:00Z    |
    When I run "kanbus router plan --json"
    Then eligible package order should be "kbs-150, kbs-151, kbs-152"

  Scenario: Human-owned active, review, and blocked issues do not consume router WIP
    Given project WIP limit is 3
    And project issues in router WIP statuses are:
      | issue_id | status      | assignee          |
      | kbs-160  | in_progress | human@example.com |
      | kbs-161  | review      | human@example.com |
      | kbs-162  | blocked     |                 |
    And pending issue "kbs-163" has routing label "agent-provider:codex-default"
    When I run "kanbus router plan --json"
    Then issue "kbs-163" should be eligible with provider profile "codex-default"

  Scenario: Only routable leaf packages consume project WIP
    Given project WIP limit is 1
    And project issues in router WIP statuses are:
      | issue_id | status      | assignee | type       | labels                              |
      | kbs-164  | in_progress |          | epic       | agent-provider:codex-default        |
      | kbs-165  | in_progress |          | task       | agent-provider:not-configured       |
    And pending issue "kbs-166" has routing label "agent-provider:codex-default"
    When I run "kanbus router plan --json"
    Then issue "kbs-166" should be eligible with provider profile "codex-default"

  Scenario: An active routable leaf package consumes project WIP
    Given project WIP limit is 1
    And project issues in router WIP statuses are:
      | issue_id | status      | assignee | type | labels                       |
      | kbs-167  | in_progress |          | task | agent-provider:codex-default |
    And pending issue "kbs-168" has routing label "agent-provider:codex-default"
    When I run "kanbus router plan --json"
    Then issue "kbs-168" should be deferred with reason "project_wip_limit"

  Scenario Outline: Each WIP limit has a stable deferral reason
    Given pending issue "kbs-170" has routing label "<route>"
    And only the "<limit>" WIP limit is reached
    When I run "kanbus router plan --json"
    Then issue "kbs-170" should be deferred with reason "<reason>"

    Examples:
      | route                           | limit    | reason            |
      | agent-provider:codex-default    | project  | project_wip_limit |
      | agent-provider:codex-default    | review   | review_wip_limit  |
      | agent-class:implementation      | class    | class_wip_limit   |
      | agent-provider:codex-default    | provider | provider_wip_limit|

  Scenario: Deferred reasons use deterministic precedence
    Given a pending package is paused, held, invalidly routed, dependency blocked, policy rejected, in retry backoff, and over every WIP limit
    When I run "kanbus router plan --json"
    Then its deferred reason should be "paused"
    And deferred reasons should use this precedence:
      | precedence | reason            |
      | 1          | paused            |
      | 2          | held              |
      | 3          | invalid_route     |
      | 4          | dependency_blocked|
      | 5          | policy_rejected   |
      | 6          | retry_backoff     |
      | 7          | project_wip_limit |
      | 8          | review_wip_limit  |
      | 9          | class_wip_limit   |
      | 10         | provider_wip_limit|

  Scenario: A blocked dependency and rejected project policy prevent dispatch
    Given pending issue "kbs-180" has routing label "agent-provider:codex-default"
    And issue "kbs-180" has an unresolved blocking dependency
    And pending issue "kbs-181" has routing label "agent-provider:codex-default"
    And project policy rejects issue "kbs-181" for router dispatch
    When I run "kanbus router plan --json"
    Then issue "kbs-180" should be deferred with reason "dependency_blocked"
    And issue "kbs-181" should be deferred with reason "policy_rejected"

  Scenario: Text planning output is deterministic
    Given one eligible package "kbs-190" routed to class "implementation" using provider profile "codex-default"
    When I run "kanbus router plan"
    Then stdout should equal:
      """
      Eligible:
        kbs-190 route=class:implementation provider=codex-default package=kbs-190 pending_since=2026-09-17T10:00:00Z attempt=1
      Deferred:
        none
      Summary: eligible=1 deferred=0 paused=false
      """
