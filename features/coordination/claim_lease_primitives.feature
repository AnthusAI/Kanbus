Feature: Coordination claim and lease primitives
  As a distributed worker
  I want a transport-independent claim and lease protocol
  So that resource ownership is explicit without replacing Git as durable history

  Collision rule: when several claims for one resource arrive inside the same
  contention window, the winner is the claim with the lexicographically
  smallest tuple of claim id, then owner, then event id. Later claims do not
  displace the winner until its lease expires or is released.

  Background:
    Given a Kanbus project with default configuration
    And coordination is configured with contention window "5s" and default lease TTL "300s"

  Scenario: A coordination claim requires resource, owner, and claim identifiers
    When I run "kanbus coordination claim --resource tts:render-1 --owner worker-local --claim-id claim-a1"
    Then the command should succeed
    And coordination lease "tts:render-1" should have owner "worker-local"
    And coordination lease "tts:render-1" should have claim id "claim-a1"

  Scenario: Contention window duration is independent of lease TTL
    Given coordination is configured with contention window "2s" and default lease TTL "600s"
    When two workers submit competing coordination claims for resource "tts:render-2" within the contention window
    Then both claims are recorded in the contention window for resource "tts:render-2"
    And the winning lease TTL should be "600s" not "2s"

  Scenario: Deterministic tie-break selects one winner inside the contention window
    Given worker "worker-alpha" submits coordination claim id "claim-0002" for resource "tts:render-3"
    And worker "worker-beta" submits coordination claim id "claim-0001" for resource "tts:render-3" within the contention window
    When the contention window closes for resource "tts:render-3"
    Then coordination lease "tts:render-3" should have claim id "claim-0001"
    And coordination lease "tts:render-3" should have owner "worker-beta"

  Scenario: Heartbeat renewal extends lease expiration without changing the winner
    Given coordination lease "tts:render-4" is held by owner "worker-a" with claim id "claim-live"
    And the lease expires at "2099-06-01T00:05:00Z"
    When I run "kanbus coordination renew --resource tts:render-4 --owner worker-a --claim-id claim-live --extend 120s"
    Then the command should succeed
    And coordination lease "tts:render-4" should expire after "2099-06-01T00:05:00Z"

  Scenario: Renewal with a mismatched owner or claim id is rejected
    Given coordination lease "tts:render-5" is held by owner "worker-a" with claim id "claim-live"
    When I run "kanbus coordination renew --resource tts:render-5 --owner worker-b --claim-id claim-live"
    Then the command should fail with exit code 1
    And stderr should contain "lease owner mismatch"

  Scenario: Expired lease returns the resource to eligibility
    Given coordination lease "tts:render-6" expired at "2099-06-01T00:00:00Z"
    When I run "kanbus coordination inspect --resource tts:render-6"
    Then stdout should contain "eligible"
    And stdout should not contain "active lease"

  Scenario: Release completes work and clears the live lease
    Given coordination lease "tts:render-7" is held by owner "worker-a" with claim id "claim-done"
    When I run "kanbus coordination release --resource tts:render-7 --owner worker-a --claim-id claim-done"
    Then the command should succeed
    And coordination lease "tts:render-7" should not be active

  Scenario: Git-only provider tolerates duplicate claims after partition
    Given coordination providers are configured as "git"
    When worker "worker-east" runs "kanbus coordination claim --resource tts:render-8 --owner worker-east --claim-id claim-east"
    And worker "worker-west" runs "kanbus coordination claim --resource tts:render-8 --owner worker-west --claim-id claim-west" after a simulated Git partition heals
    Then both coordination claims for resource "tts:render-8" should succeed
    And Git history for resource "tts:render-8" should contain both claim events

  Scenario: Lost renewal eventually expires the lease
    Given coordination lease "tts:render-9" is held by owner "worker-a" with claim id "claim-stale"
    And no renewal occurs before lease expiration
    When simulated time advances past the lease expiration
    Then coordination lease "tts:render-9" should not be active
