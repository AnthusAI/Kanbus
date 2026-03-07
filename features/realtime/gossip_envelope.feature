Feature: Gossip envelope
  Scenario: Publish an issue mutation with full snapshot
    Given a gossip issue "kanbus-123" updated at "2099-01-01T00:00:00Z"
    When I build a gossip envelope for the issue
    Then the envelope includes standard metadata fields
    Then the envelope includes the issue snapshot

  Scenario: Dedupe and ignore self
    Given a gossip receiver with producer id "p1"
    And it has already seen notification id "n1"
    When it receives notification id "n1" from producer "p2"
    Then the notification is ignored
    When it receives notification id "n2" from producer "p1"
    Then the notification is ignored
