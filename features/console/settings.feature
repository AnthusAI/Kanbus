@console
Feature: Console settings
  As a Kanbus user
  I want appearance settings
  So that the console matches my preferences

  Scenario: Settings persist in local storage
    Given the console is open
    And local storage is cleared
    When I open settings
    And I set the theme to "warm"
    And I set the mode to "dark"
    And I set the typeface to "mono"
    And I set motion to "off"
    And the console is reloaded
    Then the theme should be "warm"
    And the mode should be "dark"
    And the typeface should be "mono"
    And the motion mode should be "off"

  Scenario: Newsprint board style persists and scopes the page
    Given the console is open
    And local storage is cleared
    When I open settings
    And I set the board style to "newsprint"
    Then the board style should be "newsprint"
    And the page should carry the "newsprint" board style scope
    When the console is reloaded
    Then the board style should be "newsprint"
    And the page should carry the "newsprint" board style scope

  Scenario: Organizer board style persists and scopes the page
    Given the console is open
    And local storage is cleared
    When I open settings
    And I set the board style to "organizer"
    Then the board style should be "organizer"
    And the page should carry the "organizer" board style scope
    When the console is reloaded
    Then the board style should be "organizer"
    And the page should carry the "organizer" board style scope

  Scenario: Returning to the default board style removes the scope
    Given the console is open
    And local storage is cleared
    When I open settings
    And I set the board style to "organizer"
    And I set the board style to "default"
    Then the board style should be "default"
    And the page should carry the "default" board style scope

  Scenario: Motion off disables selector animation
    Given the console is open
    When I open settings
    And I set motion to "off"
    Then the motion mode should be "off"
