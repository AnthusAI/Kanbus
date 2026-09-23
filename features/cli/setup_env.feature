Feature: Setup machine-wide environment values
  As a Kanbus user
  I want to store any Kanbus environment value once at the user level
  So that settings such as the realtime broker apply to every clone and worktree

  Scenario: Store a value in the user-level env file
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    When I run "kanbus setup env KANBUS_REALTIME_BROKER --value mqtt://127.0.0.1:1883"
    Then the command should succeed
    And stdout should contain "Saved KANBUS_REALTIME_BROKER to ~/.kanbus.env"
    And the congregation env file should contain "KANBUS_REALTIME_BROKER=mqtt://127.0.0.1:1883"
    And the congregation env file should have mode 600

  Scenario: Update an existing value while preserving other lines
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    And the congregation env file contains:
      """
      # machine-wide settings
      OPENAI_API_KEY=keep-me
      KANBUS_REALTIME_BROKER=mqtt://127.0.0.1:1883
      """
    When I run "kanbus setup env KANBUS_REALTIME_BROKER --value mqtts://broker.example.com:8883"
    Then the command should succeed
    And the congregation env file should contain "# machine-wide settings"
    And the congregation env file should contain "OPENAI_API_KEY=keep-me"
    And the congregation env file should contain "KANBUS_REALTIME_BROKER=mqtts://broker.example.com:8883"
    And the congregation env file should not contain "mqtt://127.0.0.1:1883"

  Scenario: Status reports the source without printing the value
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    And KANBUS_REALTIME_MQTT_API_TOKEN is absent from the process environment
    And the congregation env file contains:
      """
      KANBUS_REALTIME_MQTT_API_TOKEN=secret-token-456
      """
    When I run "kanbus setup env KANBUS_REALTIME_MQTT_API_TOKEN --status"
    Then the command should succeed
    And stdout should contain "KANBUS_REALTIME_MQTT_API_TOKEN: ~/.kanbus.env"
    And stdout should not contain "secret-token-456"

  Scenario: Status reports when a value is not set
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    And KANBUS_REALTIME_BROKER is absent from the process environment
    When I run "kanbus setup env KANBUS_REALTIME_BROKER --status"
    Then the command should succeed
    And stdout should contain "KANBUS_REALTIME_BROKER: not set"
    And stdout should contain "setup env KANBUS_REALTIME_BROKER"

  Scenario: Setup env fails without a value when not interactive
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    When I run "kanbus setup env KANBUS_REALTIME_BROKER" non-interactively
    Then the command should fail with exit code 1
    And stderr should contain "no value provided"

  Scenario: Setup env rejects an invalid variable name
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    When I run "kanbus setup env not-a-variable --value x" non-interactively
    Then the command should fail with exit code 1
    And stderr should contain "invalid variable name"
