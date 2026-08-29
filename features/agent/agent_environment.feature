Feature: Agent metadata environment resolution
  As a Kanbus maintainer
  I want agent metadata resolved from environment variables
  So that agents can auto-tag mutations without repeating flags

  Scenario: Agent platform from environment when flag omitted
    Given KANBUS_AGENT_PLATFORM is set to "antigravity"
    And KANBUS_AGENT_MODEL is set to "composer-2.5"
    When I resolve agent metadata with no CLI overrides
    Then the resolved agent platform should be "antigravity"
    And the resolved agent model should be "composer-2.5"

  Scenario: Whitespace agent platform override is ignored
    Given KANBUS_AGENT_PLATFORM is set to "   "
    When I resolve agent metadata with no CLI overrides
    Then agent metadata should be absent
