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
    And the wiki storage is empty
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

  @wiki-ui-023
  Scenario: delete selected page recovers the next remaining page
    Given the console is open
    And the wiki storage is empty
    And a wiki page "draft.md" exists with content:
      """
      Leftover
      """
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

  @wiki-ui-013
  Scenario: existing wiki pages are listed instead of a false empty directory
    Given the console is open
    And a wiki page "notes.md" exists with content:
      """
      Notes body
      """
    When I switch to the "Wiki" view
    Then the wiki page list should include "notes.md"
    And the wiki empty state should not be visible

  @wiki-ui-014
  Scenario: wiki home lists titled pages when index.md exists
    Given the console is open
    And a wiki page "index.md" exists with content:
      """
      # Taskulus Wiki
      Welcome.
      """
    And a wiki page "blocked_issues.md" exists with content:
      """
      # Blocked issues
      Open items that cannot move.
      """
    When I switch to the "Wiki" view
    Then the wiki directory listing should show "Taskulus Wiki"
    And the wiki directory listing should show "Blocked issues"
    And the wiki directory listing should not show "index.md"
    And the wiki directory listing should not show "blocked_issues.md"
    And the wiki empty state should not be visible

  @wiki-ui-015
  Scenario: missing wiki directory is distinct from an empty wiki
    Given the console is open
    And the console wiki directory is missing
    When I switch to the "Wiki" view
    Then the wiki missing-directory state should be visible
    And the wiki empty state should not be visible

  @wiki-ui-016
  Scenario: wiki pages request failure shows a visible error
    Given the console is open
    And the console wiki pages request fails
    When I switch to the "Wiki" view
    Then the wiki error banner should contain "wiki pages request failed"
    And the wiki empty state should not be visible

  @wiki-ui-017
  Scenario: hung wiki pages request shows a visible error
    Given the console is open
    And the console wiki pages request hangs
    When I switch to the "Wiki" view
    Then the wiki error banner should contain "wiki pages request failed"
    And the wiki empty state should not be visible

  @wiki-ui-018
  Scenario: wiki directory listing shows H1 title instead of filename
    Given the console is open
    And a wiki page "blocked_issues.md" exists with content:
      """
      # Blocked issues
      Open items that cannot move.
      """
    When I switch to the "Wiki" view
    Then the wiki directory listing should show "Blocked issues"
    And the wiki directory listing should not show "blocked_issues.md"

  @wiki-ui-019
  Scenario: wiki directory listing shows frontmatter title instead of H1
    Given the console is open
    And a wiki page "epic_progress.md" exists with content:
      """
      ---
      title: Epic progress
      ---
      # Ignored heading
      Status body
      """
    When I switch to the "Wiki" view
    Then the wiki directory listing should show "Epic progress"
    And the wiki directory listing should not show "epic_progress.md"
    And the wiki directory listing should not show "Ignored heading"

  @wiki-ui-020
  Scenario: wiki directory listing falls back to file stem without title
    Given the console is open
    And a wiki page "untitled_notes.md" exists with content:
      """
      Just a paragraph with no heading.
      """
    When I switch to the "Wiki" view
    Then the wiki directory listing should show "untitled_notes"
    And the wiki directory listing should not show "untitled_notes.md"

  @wiki-ui-021
  Scenario: clicking a titled wiki page still navigates by path
    Given the console is open
    And a wiki page "blocked_issues.md" exists with content:
      """
      # Blocked issues
      Open items that cannot move.
      """
    When I switch to the "Wiki" view
    And I select the wiki page titled "Blocked issues"
    Then the wiki editor path should be "blocked_issues.md"

  @wiki-ui-022
  Scenario: clicking the index listing entry opens index.md
    Given the console is open
    And a wiki page "index.md" exists with content:
      """
      # Taskulus Wiki
      Welcome.
      """
    When I switch to the "Wiki" view
    And I select the wiki page titled "Taskulus Wiki"
    Then the wiki editor path should be "index.md"
