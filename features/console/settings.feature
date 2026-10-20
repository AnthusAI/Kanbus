@console
Feature: Console settings
  As a Kanbus user
  I want appearance settings
  So that the console matches my preferences

  Scenario: The console starts in the default theme
    Given the console is open
    And local storage is cleared
    When the console is reloaded
    Then the board theme should be "newspaper-gothic"

  Scenario Outline: Each board theme can be chosen in light and dark mode
    Given the console is open
    And local storage is cleared
    When I open settings
    And I set the theme to "<theme>"
    And I set the mode to "<mode>"
    Then the board theme should be "<theme>"
    And the console color mode should be "<mode>"
    And the settings panel lists the themes "Refined Newsprint, Newspaper Gothic, Night Desk, Broadsheet Green"

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

  Scenario: Theme and mode persist across a reload
    Given the console is open
    And local storage is cleared
    When I open settings
    And I set the theme to "broadsheet-green"
    And I set the mode to "dark"
    And I set motion to "off"
    And the console is reloaded
    Then the theme should be "broadsheet-green"
    And the board theme should be "broadsheet-green"
    And the mode should be "dark"
    And the console color mode should be "dark"
    And the motion mode should be "off"

  Scenario: Motion off disables selector animation
    Given the console is open
    When I open settings
    And I set motion to "off"
    Then the motion mode should be "off"
