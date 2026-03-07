Feature: Overlay cache
  Scenario: Overlay issue overrides base when newer
    Given a base issue "kanbus-1" updated at "2099-01-01T00:00:00Z"
    And an overlay issue "kanbus-1" updated at "2099-01-01T01:00:00Z"
    When I resolve the overlay issue
    Then the overlay version is returned

  Scenario: Overlay GC removes stale snapshots
    Given a base issue "kanbus-2" updated at "2099-01-02T00:00:00Z"
    And an overlay snapshot "kanbus-2" updated at "2099-01-01T23:00:00Z"
    When I run overlay GC
    Then the overlay snapshot "kanbus-2" is removed
