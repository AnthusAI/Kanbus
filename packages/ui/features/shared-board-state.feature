Feature: Shared board interaction state
  Every consumer receives the same complete board behavior without implementing toggles.

  Scenario: An embedded collection owns column collapse without host callbacks
    Given a host application with article and task issues
    When the host renders an article board
    Then the column "Draft" can be collapsed
    When I collapse column "Draft" with the keyboard
    Then column "Draft" is collapsed
    When I expand column "Draft"
    Then column "Draft" is expanded

  Scenario: The standalone shared board owns column collapse without host callbacks
    Given a host application with article and task issues
    When the host renders a standalone board
    Then the column "Open" can be collapsed
    When I collapse column "Open" with the keyboard
    Then column "Open" is collapsed

  Scenario Outline: Console and embedded consumers share configured and persistent interactions
    Given the shared board consumer "<consumer>" at width <width>
    Then column "Published" is collapsed
    When I collapse column "Draft" with the keyboard
    Then column "Draft" is collapsed
    And the collapsed column "Draft" reclaims its width
    When I reload the same shared board consumer
    Then column "Draft" is collapsed
    When I expand column "Draft"
    Then column "Draft" is expanded
    When I select a shared card with the keyboard
    Then the shared detail can close with Escape
    Examples:
      | consumer | width |
      | console  | 1440  |
      | console  | 390   |
      | embedded | 1440  |
      | embedded | 390   |

  Scenario: Unavailable browser storage does not disable the board
    Given a shared board consumer with unavailable storage
    Then column "Published" is collapsed
    When I collapse column "Draft" with the keyboard
    Then column "Draft" is collapsed

  Scenario: Malformed saved preferences use configuration defaults
    Given a shared board consumer with malformed preferences
    Then column "Published" is collapsed
    And the column "Draft" can be collapsed
