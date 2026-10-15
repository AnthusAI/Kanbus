Feature: Reuse an organizer-themed issue board in a host application
  The host controls data, navigation and playback. The shared components own
  card rendering, configured columns, accessible controls and optional styling.

  Scenario: Organizer style is optional and isolated
    Given a host application with article and task issues
    When the host renders the organizer board
    Then the organizer has square outlined cards and folder headers
    And the host route and outside content remain unchanged
    And the collection has made no API requests
    When the host renders an article board
    Then the default cards retain their rounded appearance

  Scenario: Keyboard users can collapse and reopen a column
    Given a host application with article and task issues
    When the host renders the organizer board
    And I collapse and reopen the Draft column with the keyboard
    Then issue "article-1" appears in column "draft"
    And the activated control has a visible focus indicator

  Scenario: A card opens the shared transport-free detail panel
    Given a host application with article and task issues
    When the host renders the organizer board
    And I select issue "article-1" with the keyboard
    Then the shared detail panel shows the original title and host fields
    And the collection has made no API requests
    When I close the shared detail panel
    Then focus returns to the selected card

  Scenario Outline: Organizer respects narrow layouts and color modes
    Given a host application with article and task issues
    When the host renders the organizer at width <width> in <mode> mode
    Then the board starts at its first column without page overflow
    And the organizer uses <mode> colors
    And issue cards have no reduced-motion animation
    Examples:
      | width | mode  |
      | 375   | light |
      | 1024  | dark  |

  Scenario: Default and preserved initial scrolling remain available
    Given a host application with article and task issues
    When the host renders a narrow default board
    Then the board starts at its final column
    When the host preserves a board scroll position
    Then its scroll position stays unchanged on issue updates
