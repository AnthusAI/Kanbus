Feature: Board column near end callback
  A host that pages issues by column passes onColumnNearEnd to Board or IssueCollection.
  The callback receives the column key when the last loaded card of the column is within
  columnNearEndThreshold cards (default 10) of the end of the rendered range. It works the
  same in the side by side layout and in the stacked layout, and it reports each column at
  most once for a given number of loaded issues.

  Scenario Outline: Scrolling to the end of a column fires once for that column
    Given a host application with article and task issues
    When the host renders a paged board of sections data at <width> by <height>
    Then there are no near end calls
    When I scroll the "draft" cards until the issue card "draft-60" is displayed
    Then the near end calls are "draft"
    When I scroll the "draft" cards a little further
    Then the near end calls are "draft"

    Examples:
      | width | height | layout  |
      | 1200  | 800    | columns |
      | 375   | 800    | stacked |

  Scenario Outline: Short columns that are fully visible fire once and an empty column does not fire
    Given a host application with article and task issues
    When the host renders a paged board of articles data at <width> by <height>
    Then the near end calls are "draft, review"
    When the host replaces every issue with a copy
    Then the near end calls are "draft, review"

    Examples:
      | width | height | layout  |
      | 1200  | 800    | columns |
      | 375   | 800    | stacked |

  Scenario Outline: Adding cards lets the column fire again at the new end but copies with the same count do not
    Given a host application with article and task issues
    When the host renders a paged board of sections data at <width> by <height>
    And I scroll the "draft" cards until the issue card "draft-60" is displayed
    And the host replaces every issue with a copy
    Then the near end calls are "draft"
    When the host appends 20 issues to the status "draft"
    Then the near end calls are "draft"
    When I scroll the "draft" cards until the issue card "draft-80" is displayed
    Then the near end calls are "draft, draft"

    Examples:
      | width | height | layout  |
      | 1200  | 800    | columns |
      | 375   | 800    | stacked |

  Scenario Outline: A collapsed column does not fire until it is expanded
    Given a host application with article and task issues
    When the host renders a paged board of articles data at <width> by <height> with draft collapsed
    Then the near end calls are "review"
    When I expand column "Draft"
    Then the near end calls are "draft, review"

    Examples:
      | width | height | layout  |
      | 1200  | 800    | columns |
      | 375   | 800    | stacked |

  Scenario Outline: A selected card at the end of a column that was never reached does not make it fire
    Given a host application with article and task issues
    When the host renders a paged board of sections data at <width> by <height> with issue "review-60" selected
    Then the issue card "review-60" is displayed
    And there are no near end calls
    When the host replaces every issue with a copy
    Then there are no near end calls

    Examples:
      | width | height | layout  |
      | 1200  | 800    | columns |
      | 375   | 800    | stacked |

  Scenario: A larger threshold fires earlier in the side by side layout
    Given a host application with article and task issues
    When the host renders a paged board of sections data at 1200 by 800 with threshold 100
    Then the near end calls are "draft, review, published"

  Scenario: Crossing the layout breakpoint does not throw and does not report a column again
    Given a host application with article and task issues
    When the host renders a paged board of sections data at 1200 by 800
    And I scroll the "draft" cards until the issue card "draft-60" is displayed
    Then the near end calls are "draft"
    When the viewport becomes 400 by 800
    Then the board layout is "stacked"
    And the near end calls are "draft"
    When the viewport becomes 1200 by 800
    Then the board layout is "columns"
    And the near end calls are "draft"
    And the board raised no page errors
