Feature: Current user identification
  As a Kanbus user
  I want the current user to be resolved consistently
  So that automatic attribution is predictable

  Scenario: Kanbus user override is used when set
    Given KANBUS_USER is set to "dev@example.com"
    And USER is set to "shell@example.com"
    When I resolve the current user
    Then the current user should be "dev@example.com"

  Scenario: Whitespace override is ignored
    Given KANBUS_USER is set to "   "
    And USER is set to "shell@example.com"
    When I resolve the current user
    Then the current user should be "shell@example.com"

  Scenario: Missing environment values fall back to unknown
    Given KANBUS_USER is unset
    And USER is unset
    When I resolve the current user
    Then the current user should be "unknown"
