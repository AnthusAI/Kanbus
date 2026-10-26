Feature: CLI realtime defaults
  The CLI never discovers, starts or waits for a realtime broker by default.
  Only an explicitly configured broker receives issue events from the CLI, and
  the publish never holds a command open for longer than its cap. The console
  keeps broker discovery and autostart.

  Scenario: CLI create with broker auto neither discovers nor publishes to a broker
    Given a Kanbus project with default configuration
    And a stub MQTT broker on a free port
    And broker discovery points at the stub MQTT broker
    And the environment variable "KANBUS_REALTIME_BROKER" is set to "auto"
    When I run "kanbus create Quiet auto broker"
    Then the command should succeed
    And the stub MQTT broker should have received no connections
    And stderr should not contain "realtime"

  Scenario: CLI create with broker auto never starts a broker even when autostart is requested
    Given a Kanbus project with default configuration
    And broker discovery points at a closed port
    And a mosquitto executable that records its launches
    And realtime autostart is requested
    And the environment variable "KANBUS_REALTIME_BROKER" is set to "auto"
    When I run "kanbus create No broker autostart"
    Then the command should succeed
    And no mosquitto launch should have been recorded
    And stderr should not contain "realtime"

  Scenario: CLI create with an explicit broker publishes the issue event
    Given a Kanbus project with default configuration
    And a stub MQTT broker on a free port
    And the realtime broker is the stub MQTT broker
    When I run "kanbus create Explicit broker event"
    Then the command should succeed
    And the stub MQTT broker should receive an "issue.mutated" event for the issue titled "Explicit broker event"

  Scenario: CLI create with an explicit broker that refuses connections warns and succeeds
    Given a Kanbus project with default configuration
    And the realtime broker is a closed port
    When I run "kanbus create Refused broker" and time it
    Then the command should succeed
    And stderr should contain "warning: realtime publish failed"
    And the command should have finished within 4 seconds

  Scenario: CLI create with an explicit broker that never answers finishes within the cap and warns
    Given a Kanbus project with default configuration
    And an MQTT broker on a free port that accepts connections and never answers
    And the realtime broker is the stub MQTT broker
    When I run "kanbus create Silent broker" and time it
    Then the command should succeed
    And stderr should contain "warning: realtime publish abandoned after 2s"
    And the command should have finished within 4 seconds

  Scenario: CLI create with the broker off publishes nothing
    Given a Kanbus project with default configuration
    And a stub MQTT broker on a free port
    And broker discovery points at the stub MQTT broker
    And the environment variable "KANBUS_REALTIME_BROKER" is set to "off"
    When I run "kanbus create Realtime off"
    Then the command should succeed
    And the stub MQTT broker should have received no connections
