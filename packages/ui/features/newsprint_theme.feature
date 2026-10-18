Feature: Newsprint board theme for editorial hosts
  A host opts in with data-kanbus-theme="newsprint". Boards, cards, the detail
  panel and filters then read as printed newsprint: square, ruled, full-ink text,
  and selection shown by rule and weight instead of inverted colors.

  Scenario: Cards are ruled, square and lead with a tight eyebrow
    Given a host application with article and task issues
    When the host renders the newsprint board at width 1024 in light mode
    Then no element under the newsprint theme has a border radius
    And a single rule separates adjacent cards in the Draft column
    And the issue id eyebrow sits directly above the headline on "article-1"

  Scenario: Selection is a left bar and bold weight, not an inverted card
    Given a host application with article and task issues
    When the host renders the newsprint board at width 1024 in light mode
    And I select issue "article-1" with the keyboard
    Then issue "article-1" shows a left selection bar and a heavier headline
    And issue "article-1" keeps a transparent background
    And the newsprint detail panel is square with a double rule under its heading

  Scenario: A card excerpt is clamped to three lines and toggles without selecting
    Given a host application with article and task issues
    When the host renders the newsprint board at width 1024 in light mode
    Then the excerpt on "article-1" is clamped to three lines with a More control
    When I press More on the excerpt of "article-1"
    Then the excerpt on "article-1" is fully shown with a Less control
    And issue "article-1" is not selected

  Scenario Outline: Newsprint text meets WCAG AA contrast in both modes
    Given a host application with article and task issues
    When the host renders the newsprint board at width 1024 in <mode> mode
    Then every newsprint text color has at least 4.5 to 1 contrast against the paper
    Examples:
      | mode  |
      | light |
      | dark  |
