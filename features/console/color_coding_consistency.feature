@console
Feature: Console color coding consistency
  As a Kanbus user
  I want color-coded elements to use the coded color as background and normal text as foreground
  So that styling is consistent and readable in both light and dark mode

  Scenario: Priority on card and detail view is shown as pill with background color and normal text
    Given the console is open
    When I view an issue card or detail that shows priority
    Then the priority label should use the priority color as background
    And the priority label text should use the normal text foreground color
