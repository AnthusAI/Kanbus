Feature: Mutex API acquire renew release inspect
  As a Kanbus Mutex API client
  I want hard mutual exclusion for live leases only
  So that exactly one worker owns a resource until release or expiration

  The store holds live leases only, never Kanbus history. Abandoned leases
  expire and are garbage-collected by the store's time-to-live mechanism, which
  is DynamoDB TTL when that provider is configured.

  Background:
    Given a Kanbus project with default configuration
    And coordination mutex API endpoint is "https://mutex.example.test"
    And mutex API live lease storage is empty

  Scenario: Acquire creates a live lease when the resource is free
    When mutex API client acquires resource "sched:epoch-1" for owner "worker-a" with claim id "claim-001" revision 7 lease TTL "300s"
    Then mutex API acquire response status should be 201
    And mutex API live lease for "sched:epoch-1" should include owner "worker-a"
    And mutex API live lease for "sched:epoch-1" should include claim id "claim-001"
    And mutex API live lease for "sched:epoch-1" should include revision 7
    And mutex API live lease for "sched:epoch-1" should include claimed_at timestamp
    And mutex API live lease for "sched:epoch-1" should include expires_at timestamp

  Scenario: Competing acquire fails the conditional check when a live lease exists
    Given mutex API live lease for "sched:epoch-2" is held by owner "worker-a" with claim id "claim-held"
    When mutex API client acquires resource "sched:epoch-2" for owner "worker-b" with claim id "claim-002" revision 1 lease TTL "300s"
    Then mutex API acquire response status should be 409
    And mutex API error message should contain "lease already held"

  Scenario: Renew extends expiration for the matching owner and claim id
    Given mutex API live lease for "sched:epoch-3" is held by owner "worker-a" with claim id "claim-renew" expiring at "2099-07-01T00:05:00Z"
    When mutex API client renews resource "sched:epoch-3" for owner "worker-a" with claim id "claim-renew" extending "120s"
    Then mutex API renew response status should be 200
    And mutex API live lease for "sched:epoch-3" should expire after "2099-07-01T00:05:00Z"

  Scenario: Renew rejects mismatched owner or claim id
    Given mutex API live lease for "sched:epoch-4" is held by owner "worker-a" with claim id "claim-live"
    When mutex API client renews resource "sched:epoch-4" for owner "worker-b" with claim id "claim-live" extending "60s"
    Then mutex API renew response status should be 403
    And mutex API error message should contain "lease owner mismatch"

  Scenario: Release deletes the live lease record
    Given mutex API live lease for "sched:epoch-5" is held by owner "worker-a" with claim id "claim-done"
    When mutex API client releases resource "sched:epoch-5" for owner "worker-a" with claim id "claim-done"
    Then mutex API release response status should be 204
    And mutex API live lease for "sched:epoch-5" should not exist

  Scenario: Inspect returns the active live lease only
    Given mutex API live lease for "sched:epoch-6" is held by owner "worker-a" with claim id "claim-inspect"
    When mutex API client inspects resource "sched:epoch-6"
    Then mutex API inspect response status should be 200
    And mutex API inspect body should contain claim id "claim-inspect"

  Scenario: Inspect reports no live lease after release or TTL expiration
    Given mutex API live lease for "sched:epoch-7" expired by TTL garbage collection
    When mutex API client inspects resource "sched:epoch-7"
    Then mutex API inspect response status should be 404
    And mutex API inspect body should contain "no live lease"

  Scenario: Mutex API stores only live coordination state not Kanbus history
    Given mutex API live lease for "sched:epoch-8" is held by owner "worker-a" with claim id "claim-live"
    When mutex API client releases resource "sched:epoch-8" for owner "worker-a" with claim id "claim-live"
    Then mutex API storage for resource "sched:epoch-8" should contain no historical claim records
