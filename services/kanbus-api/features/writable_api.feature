Feature: Authenticated applications share the Kanbus issue model
  As an application member
  I want to read and change configured Kanbus issues
  So that domain-specific applications share workflows and portable storage

  Scenario: Gateway group claims become exact board grants
    Given verified gateway claims with unrelated groups and kanbus board groups
    When the gateway represents the groups as an array, bracketed space-separated string or plain string
    Then only well-formed kanbus tenant and project groups grant boards
    And a tenant wildcard group grants every board of that tenant only

  Scenario: A configured vertical creates and advances an issue
    Given an isolated project with the prospect issue type
    When an authenticated member creates a prospect
    And advances it through a configured transition with its current revision
    Then the issue and its event history use normal Kanbus folder paths
    And the API returns the committed issue and new revision

  Scenario: Stale edits cannot overwrite another member
    Given two members read the same issue revision
    When one member changes the issue
    And the other submits the stale revision
    Then the second mutation returns a conflict
    And the first member's change and unknown raw fields remain intact

  Scenario: Generic queries select configured custom fields
    Given issues with different types, assignees and custom follow-up dates
    When a member filters by type, assignee and a custom-field upper bound
    Then only matching issues are returned in deterministic order
    And the query cursor cannot be reused with a different filter

  Scenario: Workflow and request boundaries reject invalid input
    Given an authenticated member and a configured project
    When the member requests a forbidden transition or an unknown issue type
    Then the API rejects the mutation without changing canonical files
    And protected identity, history and timestamp fields cannot be patched

  Scenario: Cloud identity requires verified gateway authorization
    Given a cloud request containing an arbitrary bearer token
    When verified gateway claims are absent or contain no kanbus group
    Then the API returns no issue data and performs no writes

  Scenario: Private local development requires an explicit secret
    Given a local API bound only to the loopback interface
    When the request does not contain the configured bearer secret
    Then the API returns no issue data and performs no writes

  Scenario: A comment is part of revision checked issue history
    Given an authenticated member and an existing issue
    When the member adds a comment using the current revision
    Then the comment records the authenticated actor
    And the normal event history contains the comment event

  Scenario: A retried create does not duplicate an issue
    Given a create operation has a durable receipt
    When the member repeats the same request and operation ID
    Then the original issue and revision are returned
    And reusing the operation ID with changed input returns a conflict

  Scenario: Unsupported policies and hooks cannot be bypassed
    Given a project contains policies or enabled lifecycle hooks
    When a member creates, patches or comments on an issue
    Then the mutation is rejected without changing the issue or history
    And browser configuration omits hook commands and runtime credentials

  Scenario: Changing a parent type preserves valid hierarchy
    Given a task has a sub-task child
    When a member changes the task into a non-parent type
    Then the mutation is rejected without changing the parent

  Scenario: Creation in the closed status applies closure metadata
    Given a workflow permits creation in the closed status
    When a member creates an issue in that status
    Then its closure timestamp records the creation time

  Scenario: Imported dotted identifiers retain ordinary issue paths
    Given an imported issue has a dotted identifier
    When a member reads and patches the issue
    Then its identifier and normal issue path are preserved

  Scenario: Custom numeric queries preserve precision
    Given issues have distinct custom integers above floating point precision
    When a member filters on an exact numeric bound
    Then only mathematically matching issues are returned

  Scenario: Revision checked deletion retains audit history and durable retries
    Given a member has a nonhierarchical issue with no children or incoming dependencies
    When the member deletes it with its current revision and operation ID
    Then the issue disappears from reads and board queries
    And its normal event history retains an issue deletion event
    And repeating the identical deletion returns the durable result
    And stale deletion or deletion of a referenced issue is rejected

  Scenario: Relationship mutations fail closed without related-record concurrency
    Given imported issues may already contain hierarchy and dependency links
    When a member creates or changes a parent link or dependency link
    Or changes a hierarchical issue type or deletes a hierarchical issue
    Then the API rejects the unsupported relationship mutation without publication
    But status and comment updates preserving imported relationships remain allowed

  Scenario: Native quoted object revisions support cloud writes
    Given the canonical backend returns a quoted opaque revision
    When a member patches, comments and deletes using the returned revision
    Then each conditional write uses the original native backend revision
    And stale revisions remain conflicts

  Scenario: Query work is bounded before hydration and mutation
    Given a board exceeds its candidate budget or history exceeds its read budget
    When a member requests even one card or an issue history
    Then the API returns a structured query_budget_exceeded error
    And board candidates are budgeted before any canonical card hydration
    And failed reference scans publish no mutations
    And accepted queries expose candidate, object and accepted byte counters

  Scenario: Receipt recovery also respects canonical read limits
    Given an issue was created and deleted with durable receipts
    And an offline create-only restore replaces its absent path with oversized content
    When the original create operation is retried
    Then its original durable result is returned with catalog repair pending
    And recovery never uses an unbounded canonical accessor

  Scenario: Imported identity mismatches cannot redirect writes
    Given two ordinary issue paths contain identical JSON naming only one issue
    When a member reads or mutates the mismatched path or queries the board
    Then the API rejects invalid_issue without rewriting either file or history

  Scenario: Generated audit history fits the same canonical object limit
    Given an issue contains a large description below the object limit
    When replacing it would generate a before-and-after event above the object limit
    Then the API rejects the request before publishing issue content or history

  Scenario: Responses fit the synchronous gateway transport
    Given matching history fits the read budget but exceeds the response budget
    When a member reads the history
    Then the API returns response_bytes instead of an oversized response
    And validation diagnostics are bounded without publishing invalid input
    And quote-heavy accepted responses remain below the gateway envelope limit

  Scenario: One deployment serves several tenants and boards
    Given two tenants with three boards in one deployment
    When a member granted one board reads and writes that board
    Then the board's issues are created and returned
    And a different board of the same tenant and any board of another tenant return an identical forbidden response

  Scenario: A tenant wildcard grants every board of that tenant
    Given a member granted every board of one tenant
    When the member reads boards of that tenant and of another tenant
    Then the tenant's boards are readable and the other tenant is forbidden

  Scenario: A cross-board list requires every named board to be granted
    Given a member granted two boards of a tenant
    When the member lists both boards together and then with an ungranted board
    Then the granted boards merge deterministically
    And the list with an ungranted board returns the same forbidden response as a missing board

  Scenario: Invalid board names are rejected before storage access
    Given a member granted every board of a tenant
    When a request names a tenant or project that violates the scope rules
    Then the API returns an invalid request error

  Scenario: A new board is usable without restarting the service
    Given a running service and a board that does not yet exist in storage
    When the board's configuration is published
    Then the next request to that board succeeds

  Scenario: Operation receipts are scoped per board
    Given the same operation identifier is used on two boards
    When each board creates an issue and one request is repeated
    Then each board holds one issue and the repeat returns that board's original issue

  Scenario: Direct invocation routes from the raw path only
    Given a hand-built HTTP API event with only a raw path and string group claim
    When the event is authenticated and handled
    Then the board in the raw path is served

  Scenario: Board storage keys are unchanged and requests touch only their board
    Given an existing board and two unrelated boards
    When the member creates an issue
    Then the board's keys follow the tenant and project prefix
    And the unrelated boards' keys are unchanged
