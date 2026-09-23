@console @kbs80
Feature: Console issue write controls
  As a Kanbus user
  I want to comment on issues and use allowed status transitions
  So that validated writes remain visible and recoverable

  There is no per-user authentication on the console's write API, in either
  the Rust `kbsc` server or the Node dev server. A remote caller cannot be
  identified or authorized, so writes are refused unless they originate from
  the machine running the console (localhost); reads remain reachable from
  other devices as before. That refusal depends on the TCP peer address,
  which cannot be forged from within a same-host BDD scenario driven over a
  real socket, so `kbsc`'s guard is covered by Rust-level tests instead
  (`require_loopback_allows_127_0_0_1_and_refuses_other_addresses` and
  `post_issue_comment_root_refuses_a_non_loopback_caller` in
  `rust/src/bin/console_local.rs`); the Node server's `requireLoopback`
  mirrors the same rule.

  Scenario: Comment and status APIs validate writes and return refreshed issues
    Given the console is open
    And the console has only these issues:
      | id             | title          | status |
      | kbs-write-open | Write controls | open   |
    When I add a comment through the issue write API for "kbs-write-open" with text "A normal reply"
    Then the issue write API response should be successful with comment "A normal reply"
    When I change status through the issue write API for "kbs-write-open" to "closed"
    Then the issue write API response should be successful with status "closed"
    When I change status through the issue write API for "kbs-write-open" to "not-a-status"
    Then the issue write API response should fail with status 400 and error containing "status"

  Scenario: A reply to a blocked agent resumes the package
    Given the console is open
    And the console has only these issues:
      | id              | title           | status  |
      | kbs-write-block | Awaiting reply | blocked |
    And the issue "kbs-write-block" has a blocked router conversation
    When I add a comment through the issue write API for "kbs-write-block" with text "Please continue"
    Then the issue write API response should be successful with comment "Please continue"
    And the issue write API response should report the agent was resumed
    And the issue write API response should include status "open"

  # A detail-panel composer wired to these endpoints (comment box, status
  # picker, pending/success/error states) is deliberately out of scope here.
  # #332's own composer touched packages/ui/src/kanban/TaskDetailPanel.tsx
  # and apps/console/src/api/client.ts against a version of develop that
  # predated the agent-assignment display (AgentAssignmentBlock); merging it
  # as-is would have deleted that shipped feature. That UI work should land
  # as its own change against current develop.
