@wip
Feature: Wiki Markus rendering pipeline
  Wiki pages render in two stages: Jinja2 evaluates templates against the live
  issue index, then anthus-markus (markusmd.convert) converts the resulting
  Markdown to semantic HTML. Unknown :::directives fail validation instead of
  being ignored. Plain GFM and existing Jinja templates remain valid.

  Story kbs-5d88eb under epic kbs-bd41d7.

  Scenario: Jinja issue-index output is converted through Markus
    Given a Kanbus project with default configuration
    And 3 open tasks and 2 closed tasks exist
    And a wiki page "status.md" with content:
      """
      Open: {{ count(status="open") }}
      Closed: {{ count(status="closed") }}
      """
    When I run "kanbus wiki render project/wiki/status.md --html"
    Then the command should succeed
    And stdout should contain "Open: 3"
    And stdout should contain "Closed: 2"
    And stdout should contain HTML element with class "markus-document"

  Scenario: Markus pull-quote directive renders through the Python path
    Given a Kanbus project with default configuration
    And a wiki page "quote.md" with content:
      """
      :::pull-quote
      > Measure what matters.
      {: attribution="Editorial principle" }
      :::
      """
    When I run "kanbus wiki render project/wiki/quote.md --html"
    Then the command should succeed
    And stdout should contain HTML element with class "markus-pull-quote"
    And stdout should contain "Measure what matters."

  Scenario: Markus card-grid renders peer cards
    Given a Kanbus project with default configuration
    And a wiki page "cards.md" with content:
      """
      :::card-grid
      :::card{title="Alpha"}
      First peer.
      :::
      :::card{title="Beta"}
      Second peer.
      :::
      :::
      """
    When I run "kanbus wiki render project/wiki/cards.md --html"
    Then the command should succeed
    And stdout should contain HTML element with class "markus-card-grid"
    And stdout should contain HTML element with class "markus-card"
    And stdout should contain "First peer."
    And stdout should contain "Second peer."

  Scenario: Wiki render JSON includes Markus HTML after Jinja
    Given a Kanbus project with default configuration
    And 3 open tasks and 2 closed tasks exist
    And a wiki page "status.md" with content:
      """
      Open: {{ count(status="open") }}

      :::pull-quote
      > Live board data first.
      :::
      """
    When I run "kanbus wiki render project/wiki/status.md --json"
    Then the command should succeed
    And stdout should be valid JSON
    And JSON field "rendered" should contain "Open: 3"
    And JSON field "rendered_html" should contain HTML element with class "markus-pull-quote"
    And JSON field "rendered_html" should contain "Open: 3"

  Scenario: Unknown Markus directive fails validation
    Given a Kanbus project with default configuration
    And a wiki page "invalid_directive.md" with content:
      """
      :::unknown-directive
      This should not render.
      :::
      """
    When I run "kanbus wiki render project/wiki/invalid_directive.md --html"
    Then the command should fail with exit code 1
    And stderr should contain "Unknown directive"

  Scenario: Plain GFM wiki page remains valid through Markus
    Given a Kanbus project with default configuration
    And a wiki page "plain.md" with content:
      """
      # Status

      Plain paragraph with **bold** text.
      """
    When I run "kanbus wiki render project/wiki/plain.md --html"
    Then the command should succeed
    And stdout should contain HTML element with class "markus-document"
    And stdout should contain "Plain paragraph with"

  Scenario: Jinja templates without Markus directives keep default markdown output
    Given a Kanbus project with default configuration
    And 3 open tasks and 2 closed tasks exist
    And a wiki page "status.md" with content:
      """
      Open: {{ count(status="open") }}
      Closed: {{ count(status="closed") }}
      """
    When I run "kanbus wiki render project/wiki/status.md"
    Then the command should succeed
    And stdout should contain "Open: 3"
    And stdout should contain "Closed: 2"
    And stdout should not contain "markus-document"
