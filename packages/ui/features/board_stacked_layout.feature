Feature: Stacked board layout
  Below a viewport width the board renders as one vertical column with each status
  column as a section. The rule is width only, so a phone in landscape and a tablet
  keep the horizontal board.

  Scenario: A 375 pixel viewport renders sections without horizontal scrolling
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 375 by 700
    Then the board layout is "stacked"
    And the board sections are "Draft, Editorial review, Published"
    And the board has no horizontal overflow
    And the issue cards are stacked vertically
    And the board has not scrolled horizontally

  Scenario Outline: The layout follows the viewport width alone
    Given a host application with article and task issues
    When the host renders a stacked board of articles at <width> by <height>
    Then the board layout is "<layout>"

    Examples:
      | width | height | layout  |
      | 1024  | 768    | columns |
      | 768   | 1024   | columns |
      | 667   | 375    | columns |
      | 600   | 800    | columns |
      | 599   | 800    | stacked |
      | 375   | 812    | stacked |

  Scenario: The desktop layout keeps side by side columns with their own scrollers
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 1024 by 768
    Then the board layout is "columns"
    And the board columns are "Draft, Editorial review, Published"
    And the board columns sit side by side
    And no stacked scroller is rendered

  Scenario: Resizing across the breakpoint switches layout and keeps the selection
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 1024 by 768
    And I select issue "article-3" with the keyboard
    And the viewport becomes 400 by 800
    Then the board layout is "stacked"
    And the issue card "article-3" is selected
    When the viewport becomes 1024 by 768
    Then the board layout is "columns"
    And the issue card "article-3" is selected

  Scenario: The layout prop overrides the viewport
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 375 by 700 with layout "columns"
    Then the board layout is "columns"
    When the host renders a stacked board of articles at 1024 by 768 with layout "stacked"
    Then the board layout is "stacked"

  Scenario: The stackedBelowWidth prop changes the threshold
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 800 by 800
    Then the board layout is "columns"
    When the host renders a stacked board of articles at 800 by 800 with stackedBelowWidth 900
    Then the board layout is "stacked"

  Scenario: A standalone Board accepts the same layout props
    Given a host application with article and task issues
    When the host renders a standalone stacked Board at 375 by 700
    Then the board layout is "stacked"
    And the board sections are "Draft, Editorial review, Published"

  Scenario: A section with 500 issues renders a bounded number of cards and scrolls to its last card
    Given a host application with article and task issues
    When the host renders a stacked board of large data at 375 by 700
    Then at most 40 issue cards are rendered
    When I scroll the stacked board to its end
    Then the issue card "bulk-500" is displayed
    And at most 40 issue cards are rendered

  Scenario: The selected card stays rendered and in place after a detail panel opens and closes
    Given a host application with article and task issues
    When the host renders a stacked board of large data at 375 by 700
    And I scroll the stacked board by 3000 pixels
    And I remember the position of the first visible issue card
    And I select the first visible issue card with the keyboard
    Then the remembered issue card is in its remembered position
    When I close the shared detail panel with Escape
    Then the remembered issue card is in its remembered position
    And the board has not scrolled horizontally

  Scenario: The selected card stays rendered while the board scrolls away from it
    Given a host application with article and task issues
    When the host renders a stacked board of large data at 375 by 700
    And I scroll the stacked board by 3000 pixels
    And I remember the position of the first visible issue card
    And I select the first visible issue card with the keyboard
    And I scroll the stacked board to its end
    Then the remembered issue card is displayed

  Scenario: The header of the section being scrolled through stays visible at the top
    Given a host application with article and task issues
    When the host renders a stacked board of sectioned data at 375 by 700
    And I scroll the stacked board by 2500 pixels
    Then a single section header is pinned at the top of the board
    And the pinned section header belongs to the section of the first visible card
    When I scroll the stacked board to its end
    Then the pinned section header belongs to the section of the first visible card

  Scenario: Tapping a section header collapses it to its header row
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 375 by 700
    And I collapse column "Draft" with the keyboard
    Then column "Draft" is collapsed in the stacked board
    And the stacked section "Draft" has the vertical text style disabled
    And the chevron of section "Draft" points right
    When I expand column "Draft"
    Then the chevron of section "Draft" points down
    And the issue card "article-1" is displayed

  Scenario: Collapse state is shared across layouts and persists through columnStateKey
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 375 by 700 with columnStateKey "fixture.stacked.shared.v1"
    And I collapse column "Draft" with the keyboard
    And the viewport becomes 1024 by 768
    Then the board layout is "columns"
    And column "Draft" is collapsed
    When I reload the page and render a stacked board of articles at 375 by 700 with columnStateKey "fixture.stacked.shared.v1"
    Then column "Draft" is collapsed in the stacked board

  Scenario: Configuration collapsed statuses start collapsed
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 375 by 700 with published collapsed by configuration
    Then column "Published" is collapsed in the stacked board

  Scenario: Status moves with animated motion do not throw or leave the flipping state set
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 375 by 700 with animated motion
    And the host moves stacked issue "article-1" to status "review"
    Then issue "article-1" appears in column "review"
    And the board is not flipping

  Scenario: Status moves with reduced motion do not throw or leave the flipping state set
    Given a host application with article and task issues
    When the host renders a stacked board of articles at 375 by 700 with reduced motion
    And the host moves stacked issue "article-1" to status "review"
    Then issue "article-1" appears in column "review"
    And the board is not flipping

  Scenario: Server rendering and hydration produce no React warning
    Given a host application with article and task issues
    When the host hydrates a server rendered board at 375 by 700
    Then the hydrated board layout becomes "stacked"
    And the console reported no hydration warning
