Feature: Editorial board themes for hosts and the console
  A host opts in with data-kanbus-theme="<id>" on any ancestor of the board and chooses a color
  mode with data-color-mode. Four themes are provided: refined-newsprint, newspaper-gothic,
  night-desk and broadsheet-green. Each has a light and a dark mode that share one structure:
  ruled flat cards, a quiet mono id line above a title set in the theme's title face, a 2px ink
  rule under column headers, and a left accent bar on the selected card. Hosts load the fonts and
  may override any --kb-theme-* token.

  Scenario Outline: Each theme applies its scope attributes and resolves its tokens in both modes
    Given a host application with article and task issues
    When the host renders the "<theme>" board at width 1024 in <mode> mode
    Then the theme scope carries the attributes "<theme>" and "<mode>"
    And the public color and font tokens all resolve to values
    And the board background is the theme paper
    And the card titles use the title face "<title face>"
    And the issue id line uses the mono face "<mono face>" at 10px

    Examples:
      | theme             | mode  | title face     | mono face      |
      | refined-newsprint | light | Source Serif 4 | IBM Plex Mono  |
      | refined-newsprint | dark  | Source Serif 4 | IBM Plex Mono  |
      | newspaper-gothic  | light | Libre Franklin | JetBrains Mono |
      | newspaper-gothic  | dark  | Libre Franklin | JetBrains Mono |
      | night-desk        | light | Literata       | JetBrains Mono |
      | night-desk        | dark  | Literata       | JetBrains Mono |
      | broadsheet-green  | light | Newsreader     | IBM Plex Mono  |
      | broadsheet-green  | dark  | Newsreader     | IBM Plex Mono  |

  Scenario Outline: Text, muted text, accent and accent fills meet WCAG AA in every theme and mode
    Given a host application with article and task issues
    When the host renders the "<theme>" board at width 1024 in <mode> mode
    Then ink text has at least 4.5 to 1 contrast against the paper, panel, sidebar and hovered card
    And muted text has at least 4.5 to 1 contrast against the paper, panel, sidebar and hovered card
    And the accent has at least 4.5 to 1 contrast against the paper and panel
    And text on the accent fill has at least 4.5 to 1 contrast against the accent
    And every rendered board text color has at least 4.5 to 1 contrast against the paper

    Examples:
      | theme             | mode  |
      | refined-newsprint | light |
      | refined-newsprint | dark  |
      | newspaper-gothic  | light |
      | newspaper-gothic  | dark  |
      | night-desk        | light |
      | night-desk        | dark  |
      | broadsheet-green  | light |
      | broadsheet-green  | dark  |

  Scenario Outline: Cards are flat ruled rows and columns have an ink rule
    Given a host application with article and task issues
    When the host renders the "<theme>" board at width 1024 in light mode
    Then no element under the theme has a border radius or shadow
    And a single rule separates adjacent cards in the Draft column
    And the issue id line sits directly above the headline on "article-1"
    And the Draft column header has a 2px rule and an uppercase label

    Examples:
      | theme             |
      | refined-newsprint |
      | newspaper-gothic  |
      | night-desk        |
      | broadsheet-green  |

  Scenario: Selection is a left accent bar without changing the card
    Given a host application with article and task issues
    When the host renders the "refined-newsprint" board at width 1024 in light mode
    And I select issue "article-1" with the keyboard
    Then issue "article-1" shows a 3px left accent bar
    And issue "article-1" keeps a transparent background
    And the detail panel heading has a 2px rule under it

  Scenario: A collapsed column is a 30px strip
    Given a host application with article and task issues
    When the host renders the "newspaper-gothic" board at width 1024 in light mode
    And I collapse column "Draft" with the keyboard
    Then the collapsed column "Draft" is 30px wide

  Scenario: A card excerpt is clamped to three lines and toggles without selecting
    Given a host application with article and task issues
    When the host renders the "broadsheet-green" board at width 1024 in light mode
    Then the excerpt on "article-1" is clamped to three lines with a More control
    When I press More on the excerpt of "article-1"
    Then the excerpt on "article-1" is fully shown with a Less control
    And issue "article-1" is not selected

  Scenario: System mode follows the color scheme of the visitor
    Given a host application with article and task issues
    When the host renders the "night-desk" board without a color mode while the visitor prefers light
    Then the theme scope has no color mode attribute
    And the board background is the theme paper
    And the page paper is light
    When the visitor switches to prefer dark
    Then the page paper is dark

  Scenario: A host overrides a public token
    Given a host application with article and task issues
    When the host renders the "newspaper-gothic" board with the accent token overridden
    Then the selection bar color is the overridden accent

  Scenario: The package lists the themes and the fonts each one needs
    Given a host application with article and task issues
    Then the package lists four themes with font families for each
