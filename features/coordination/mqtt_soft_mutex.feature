@wip
Feature: MQTT soft mutex fast path
  As a Kanbus worker with optional MQTT gossip
  I want fast-path claim messages during a contention window
  So that soft mutual exclusion reduces duplicate work without requiring Mosquitto for Git-only installs

  Background:
    Given a Kanbus project with default configuration
    And coordination providers are configured as "git,mqtt"
    And coordination is configured with contention window "3s" and default lease TTL "300s"
    And realtime MQTT gossip is available per docs REALTIME.md

  Scenario: CLAIM gossip announces intent during the contention window
    When worker "worker-a" publishes coordination gossip type "coordination.claim" for resource "job:fast-1" with claim id "claim-a"
    Then MQTT subscribers should receive envelope type "coordination.claim" for resource "job:fast-1"
    And the gossip envelope should follow REALTIME.md dedupe and producer rules

  Scenario: Contention window closes into LEASE for the deterministic winner
    Given worker "worker-a" published coordination gossip type "coordination.claim" for resource "job:fast-2" with claim id "claim-b"
    And worker "worker-b" published coordination gossip type "coordination.claim" for resource "job:fast-2" with claim id "claim-a" within the contention window
    When the contention window closes for resource "job:fast-2"
    Then coordination gossip type "coordination.lease" should be emitted for resource "job:fast-2" with claim id "claim-a"
    And coordination lease "job:fast-2" should have owner "worker-b"

  Scenario: RELEASE gossip clears soft mutex visibility before Git durable release lands
    Given coordination lease "job:fast-3" is held by owner "worker-a" with claim id "claim-live"
    When worker "worker-a" publishes coordination gossip type "coordination.release" for resource "job:fast-3" with claim id "claim-live"
    Then MQTT subscribers should receive envelope type "coordination.release" for resource "job:fast-3"
    And overlay merge rules from REALTIME.md should apply to speculative coordination visibility

  Scenario: MQTT partition may still duplicate work like Git-only strength
    Given coordination providers are configured as "git,mqtt"
    And MQTT partition isolates worker "worker-east" from worker "worker-west"
    When worker "worker-east" runs "kanbus coordination claim --resource job:fast-4 --owner worker-east --claim-id claim-east"
    And worker "worker-west" runs "kanbus coordination claim --resource job:fast-4 --owner worker-west --claim-id claim-west"
    Then both coordination claims for resource "job:fast-4" should succeed
    And stderr should not contain "mqtt required"
