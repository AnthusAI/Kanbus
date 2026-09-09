Feature: Optional Mosquitto warnings
  Scenario: Routine publish attempts stay quiet when Mosquitto is missing
    Given mosquitto is not available
    And realtime autostart is enabled
    When I publish gossip envelopes for two issue mutations without a broker
    Then Mosquitto install hints should not be printed

  Scenario: Realtime MQTT subscription warns once per session when Mosquitto is missing
    Given mosquitto is not available
    And realtime autostart is enabled
    When I attempt MQTT gossip subscription twice in one session
    Then Mosquitto install hints should be printed once

  Scenario: Realtime guide documents optional Mosquitto
    When I read the realtime documentation
    Then the realtime guide documents optional Mosquitto
