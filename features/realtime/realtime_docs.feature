Feature: Realtime documentation
  Scenario: Realtime guide is complete
    When I read the realtime documentation
    Then the realtime guide documents transport selection
    And the realtime guide documents broker discovery
    And the realtime guide documents autostart behavior
    And the realtime guide documents envelope schema
    And the realtime guide documents dedupe rules
    And the realtime guide documents overlay merge rules
    And the realtime guide documents overlay GC and hooks
    And the realtime guide documents CLI commands
    And the realtime guide documents config blocks
