Feature: UDS broker
  Scenario: UDS broker fans out to subscribers
    Given a running UDS gossip broker
    When a subscriber listens on "projects/kanbus/events"
    And a publisher sends a gossip envelope on "projects/kanbus/events"
    Then the subscriber receives the envelope
