Feature: MQTT autostart
  Scenario: Autostart writes broker metadata
    Given mosquitto is available
    When I autostart a mosquitto broker
    Then broker metadata is written
