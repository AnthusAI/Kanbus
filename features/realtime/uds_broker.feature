Feature: UDS broker
  Scenario: UDS broker fans out to subscribers
    Given a running UDS gossip broker
    When a subscriber listens on "projects/kanbus/events"
    And a publisher sends a gossip envelope on "projects/kanbus/events"
    Then the subscriber receives the envelope

  Scenario: UDS broker ignores blank lines and invalid JSON
    Given a running UDS gossip broker
    When a subscriber connects and sends a blank line
    Then the broker should remain running
    When a subscriber connects and sends invalid JSON
    Then the broker should remain running
