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

  Scenario: Motion off disables selector animation
    Given the console is open
    When I open settings
    And I set motion to "off"
    Then the motion mode should be "off"
