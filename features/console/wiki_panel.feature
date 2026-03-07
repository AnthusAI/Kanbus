@console
Feature: Console wiki workspace
  As a Kanbus console user
  I want a wiki workspace alongside board and metrics
  So that I can author, preview, and manage wiki pages

  @wiki-ui-001
  Scenario: switching panel mode to wiki shows workspace
    Given the console is open
    And the wiki storage is empty
    When I switch to the "Wiki" view
    Then the wiki view should be active
    And the wiki empty state should be visible

  @wiki-ui-002
  Scenario: create page from empty state
    Given the console is open
    And the wiki storage is empty
    When I switch to the "Wiki" view
    And I create a wiki page named "index.md"
    Then the wiki page list should include "index.md"
    And the wiki editor path should be "index.md"
    And the wiki editor content should equal:
      """
      # New page
      """
    And the wiki preview should contain "No preview yet"

  @wiki-ui-003
  Scenario: edit existing page and save
    Given the console is open
    And a wiki page "notes.md" exists with content:
      """
      First draft
      """
    When I switch to the "Wiki" view
    And I select wiki page "notes.md"
    And I type wiki content:
      """
      Updated content
      """
    And I save the wiki page
    Then the wiki status should show "Saved"
    And the wiki editor content should equal:
      """
      Updated content
      """

  @wiki-ui-004
  Scenario: preview dirty draft
    Given the console is open
    And a wiki page "draft.md" exists with content:
      """
      Original content
      """
    When I switch to the "Wiki" view
    And I select wiki page "draft.md"
    And I type wiki content:
      """
      Draft live
      """
    And I render the wiki page
    Then the wiki preview should contain "Draft live"
    And the wiki status should show "Unsaved changes"

  @wiki-ui-005
  Scenario: rename selected page and keep selection
    Given the console is open
    And a wiki page "page.md" exists with content:
      """
      Body
      """
    When I switch to the "Wiki" view
    And I select wiki page "page.md"
    And I rename the wiki page "page.md" to "renamed.md"
    Then the wiki page list should include "renamed.md"
    And the wiki page list should not include "page.md"
    And the wiki editor path should be "renamed.md"

  @wiki-ui-006
  Scenario: delete selected page and recover selection
    Given the console is open
    And a wiki page "first.md" exists with content:
      """
      One
      """
    And a wiki page "second.md" exists with content:
      """
      Two
      """
    When I switch to the "Wiki" view
    And I select wiki page "first.md"
    And I delete the wiki page "first.md"
    Then the wiki page list should include "second.md"
    And the wiki page list should not include "first.md"
    And the wiki editor path should be "second.md"

  @wiki-ui-007
  Scenario: invalid create path shows error banner
    Given the console is open
    And the wiki storage is empty
    When I switch to the "Wiki" view
    And I try to create a wiki page named "../bad.md"
    Then the wiki error banner should contain "wiki create request failed"

  @wiki-ui-008
  Scenario: unsaved guard blocks page switch without confirmation
    Given the console is open
    And a wiki page "first.md" exists with content:
      """
      One
      """
    And a wiki page "second.md" exists with content:
      """
      Two
      """
    When I switch to the "Wiki" view
    And I select wiki page "first.md"
    And I type wiki content:
      """
      Dirty edit
      """
    And I attempt to select wiki page "second.md" without confirming
    Then the wiki editor path should be "first.md"
    And the wiki editor content should equal:
      """
      Dirty edit
      """

  @wiki-ui-009
  Scenario: unsaved guard blocks panel switch without confirmation
    Given the console is open
    And a wiki page "stay.md" exists with content:
      """
      Sticky
      """
    When I switch to the "Wiki" view
    And I select wiki page "stay.md"
    And I type wiki content:
      """
      In progress
      """
    And I attempt to leave the wiki view without confirming
    Then the wiki view should be active
    And the wiki editor content should equal:
      """
      In progress
      """

  @wiki-ui-010
  Scenario: render error preserves last successful preview
    Given the console is open
    And a wiki page "calc.md" exists with content:
      """
      Baseline content
      """
    When I switch to the "Wiki" view
    And I select wiki page "calc.md"
    And I render the wiki page
    And I type wiki content:
      """
      {{ 1 / 0 }}
      """
    And I render the wiki page
    Then the wiki error banner should contain "division by zero"
    And the wiki preview should contain "Baseline content"

  @wiki-ui-011
  Scenario: refresh preserves panel mode selection
    Given the console is open
    When I switch to the "Wiki" view
    And the console is reloaded
    Then the wiki view should be active

  @wiki-ui-012
  Scenario: board and metrics still functional after wiki integration
    Given the console is open
    When I switch to the "Wiki" view
    And I switch to the "Board" view
    Then the board view should be active
    And the wiki view should be inactive
    When I switch to the "Metrics" view
    Then the metrics view should be active
    And the wiki view should be inactive
