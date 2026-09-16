@console
@wiki-markus
Feature: Console wiki Markus preview
  The console wiki workspace requests backend-rendered HTML that already
  includes Markus semantic classes. The browser hosts preview chrome and
  styles only; it does not parse :::directives client-side.

  Story kbs-5d88eb under epic kbs-bd41d7.

  Scenario: Wiki preview shows backend-rendered Markus HTML
    Given the console is open
    And the wiki storage is empty
    And a wiki page "quote.md" exists with content:
      """
      :::pull-quote
      > Backend renders this.
      :::
      """
    When I switch to the "Wiki" view
    And I select wiki page "quote.md"
    And I render the wiki page through the backend
    Then the wiki preview HTML should contain element with class "markus-pull-quote"
    And the wiki preview HTML should contain "Backend renders this."
    And the wiki preview HTML should not contain ":::pull-quote"

  Scenario: Wiki preview renders Markus card-grid from backend HTML
    Given the console is open
    And the wiki storage is empty
    And a wiki page "cards.md" exists with content:
      """
      :::card-grid
      :::card{title="One"}
      First card.
      :::
      :::card{title="Two"}
      Second card.
      :::
      :::
      """
    When I switch to the "Wiki" view
    And I select wiki page "cards.md"
    And I render the wiki page through the backend
    Then the wiki preview HTML should contain element with class "markus-card-grid"
    And the wiki preview HTML should contain element with class "markus-card"
    And the wiki preview HTML should not contain ":::card-grid"

  Scenario: Unknown Markus directive shows render error in console
    Given the console is open
    And the wiki storage is empty
    And a wiki page "bad.md" exists with content:
      """
      :::unknown-directive
      Invalid block.
      :::
      """
    When I switch to the "Wiki" view
    And I select wiki page "bad.md"
    And I render the wiki page through the backend
    Then the wiki error banner should contain "Unknown directive"

  Scenario: Markus render error preserves last successful preview
    Given the console is open
    And the wiki storage is empty
    And a wiki page "baseline.md" exists with content:
      """
      :::pull-quote
      > Baseline preview.
      :::
      """
    When I switch to the "Wiki" view
    And I select wiki page "baseline.md"
    And I render the wiki page through the backend
    And I type wiki content:
      """
      :::unknown-directive
      Broken draft.
      :::
      """
    And I render the wiki page through the backend
    Then the wiki error banner should contain "Unknown directive"
    And the wiki preview HTML should contain element with class "markus-pull-quote"
    And the wiki preview HTML should contain "Baseline preview."
