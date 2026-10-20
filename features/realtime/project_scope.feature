Feature: Realtime project scope
  Realtime events are published on a topic scoped by a stable project identity
  and are applied only by consumers of the same project, even when several
  projects share one broker and one project key.

  Scenario: A published mutation reaches only the topic of its own project
    Given a running UDS gossip broker
    And two projects "alpha" and "beta" that share the project key "kanbus" and the UDS broker
    And a raw subscriber on the realtime topic of project "alpha"
    And a raw subscriber on the realtime topic of project "beta"
    When project "alpha" publishes an issue mutation for "kanbus-scope1"
    Then the raw subscriber of project "alpha" receives an envelope for "kanbus-scope1"
    And the raw subscriber of project "beta" receives no envelope

  Scenario: Consumers apply only events that belong to their own project
    Given a running UDS gossip broker
    And two projects "alpha" and "beta" that share the project key "kanbus" and the UDS broker
    And a console realtime consumer for project "alpha"
    And a console realtime consumer for project "alpha"
    And a console realtime consumer for project "beta"
    When a remote producer publishes an issue mutation for "kanbus-scope2" in project "alpha"
    Then every console realtime consumer of project "alpha" applies the issue "kanbus-scope2"
    And no console realtime consumer of project "beta" applies the issue "kanbus-scope2"

  Scenario: A consumer drops an event on its own topic that carries another project's identity
    Given a running UDS gossip broker
    And two projects "alpha" and "beta" that share the project key "kanbus" and the UDS broker
    And a console realtime consumer for project "alpha"
    When a remote producer publishes an issue mutation for "kanbus-scope3" on the topic of project "alpha" claiming the identity of project "beta"
    And a remote producer publishes an issue mutation for "kanbus-scope4" in project "alpha"
    Then every console realtime consumer of project "alpha" applies the issue "kanbus-scope4"
    And no console realtime consumer of project "alpha" applies the issue "kanbus-scope3"
    And the count of dropped events for other projects has increased
