Feature: Revision-aware coordination result publication
  As a worker executing logical task revisions
  I want Kanbus to publish results by revision not finish order
  So that stale local output cannot overwrite newer work

  Background:
    Given a Kanbus project with default configuration
    And coordination is configured with default lease TTL "900s"

  Scenario: Publish accepts the first result for a resource revision
    Given logical task revision for resource "tts:voice-1" is 3
    When I run "kanbus coordination publish-result --resource tts:voice-1 --revision 3 --artifact /tmp/render-r3.mp3"
    Then the command should succeed
    And published revision for resource "tts:voice-1" should be 3

  Scenario: Publish rejects a result older than the published revision
    Given published revision for resource "tts:voice-2" is 5
    When I run "kanbus coordination publish-result --resource tts:voice-2 --revision 4 --artifact /tmp/stale.mp3"
    Then the command should fail with exit code 1
    And stderr should contain "stale revision"

  Scenario: Publish accepts a newer revision after a prior publish
    Given published revision for resource "tts:voice-3" is 2
    When I run "kanbus coordination publish-result --resource tts:voice-3 --revision 3 --artifact /tmp/render-r3.mp3"
    Then the command should succeed
    And published revision for resource "tts:voice-3" should be 3

  Scenario: Local-first worker may claim before cloud backstop eligibility
    Given coordination lease "tts:voice-4" is held by owner "worker-local" with claim id "claim-local"
    And logical task revision for resource "tts:voice-4" is 1
    When simulated time advances by "14m" without a published result
    Then cloud backstop worker should not yet be eligible for resource "tts:voice-4"

  Scenario: Cloud backstop becomes eligible after local claim timeout threshold
    Given coordination lease "tts:voice-5" is held by owner "worker-local" with claim id "claim-local"
    And backstop eligibility threshold is "15m"
    When simulated time advances by "15m" without a published result
    Then cloud backstop worker should be eligible for resource "tts:voice-5"
    And Git remains the durable history for resource "tts:voice-5"

  Scenario: Cloud backstop publish still respects revision ordering
    Given published revision for resource "tts:voice-6" is 8
    And cloud backstop worker is eligible for resource "tts:voice-6"
    When cloud worker runs "kanbus coordination publish-result --resource tts:voice-6 --revision 7 --artifact /tmp/cloud-stale.mp3"
    Then the command should fail with exit code 1
    And stderr should contain "stale revision"

  Scenario: A router result publishes checkpoint and named artifact references with its revision
    Given router package "kbs-901" has current claim "claim-r5" at logical revision 5
    When claim "claim-r5" publishes a completed result with checkpoint "refs/kanbus/router/checkpoints/kbs-901" at revision 5
    And claim "claim-r5" publishes artifact "test-report" as "refs/kanbus/router/artifacts/kbs-901/test-report-r5"
    Then the published result for package "kbs-901" should include claim "claim-r5" and revision 5
    And the published checkpoint should be "refs/kanbus/router/checkpoints/kbs-901"
    And the published artifacts should contain "test-report=refs/kanbus/router/artifacts/kbs-901/test-report-r5"
