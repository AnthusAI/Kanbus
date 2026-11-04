@console @slow @kbs-bab14c
Feature: Console board on a phone
  As a Kanbus user on a phone
  I want the console toolbar, board and issue detail to fit the screen
  So that I can browse issues and read detail without sideways scrolling

  Background:
    Given the console is open
    And the console has only these issues:
      | id         | title             | status      |
      | kbs-ph-01  | Phone issue one   | open        |
      | kbs-ph-02  | Phone issue two   | open        |
      | kbs-ph-03  | Phone issue three | open        |
      | kbs-ph-04  | Phone issue four  | open        |
      | kbs-ph-05  | Phone issue five  | open        |
      | kbs-ph-06  | Phone issue six   | open        |
      | kbs-ph-07  | Phone issue seven | open        |
      | kbs-ph-08  | Phone issue eight | open        |
      | kbs-ph-09  | Phone issue nine  | open        |
      | kbs-ph-10  | Phone issue ten   | open        |
      | kbs-ph-11  | Phone issue 11    | open        |
      | kbs-ph-12  | Phone issue 12    | open        |
      | kbs-ph-13  | Phone issue 13    | open        |
      | kbs-ph-14  | Phone issue 14    | open        |
      | kbs-ph-15  | Phone issue 15    | open        |
      | kbs-ph-16  | Phone issue 16    | open        |
      | kbs-ph-17  | Phone issue 17    | in_progress |
      | kbs-ph-18  | Phone issue 18    | in_progress |

  Scenario: The board and toolbar fit a 390 pixel wide screen
    Given the browser viewport is 390 by 844
    When I switch to the "Tasks" tab
    Then the board should render stacked
    And the page should not scroll horizontally
    And no element outside the view carousel track should be wider than the viewport
    And the console toolbar should stay inside the viewport
    And the console toolbar should not scroll horizontally
    And every console toolbar control should be reachable
    And every issue type filter tab should be visible

  Scenario: Opening an issue on a phone shows detail that fills the screen
    Given the browser viewport is 390 by 844
    When I switch to the "Tasks" tab
    And I open the task "Phone issue two"
    Then the detail panel should fill the viewport width
    And the detail panel should reach the bottom of the viewport
    And the detail close control should be inside the viewport
    And the detail resizer should not be visible
    And the page should not scroll horizontally

  Scenario: Closing detail on a phone returns to the same card
    Given the browser viewport is 390 by 844
    When I switch to the "Tasks" tab
    And I record the board vertical scroll position
    And I open the task "Phone issue two"
    And I close the detail panel
    Then the board vertical scroll position should match the recorded position
    And the task "Phone issue two" should be visible in the viewport

  Scenario: Closing detail on a scrolled long board returns to the same card
    Given the browser viewport is 390 by 844
    When I switch to the "Tasks" tab
    And I scroll the board down by 420 pixels
    And I record the board vertical scroll position
    And I open the card nearest the middle of the board
    Then the detail panel should fill the viewport width
    When I close the detail panel
    Then the board vertical scroll position should match the recorded position
    And the opened card should be visible in the viewport

  Scenario: A desktop screen keeps columns, the resizer and side by side detail
    Given the browser viewport is 1440 by 900
    When I switch to the "Tasks" tab
    Then the board should render in columns
    And the board should show more than one column side by side
    When I open the task "Phone issue two"
    Then the detail resizer should be visible
    And the detail panel should sit beside the board
    And the page should not scroll horizontally
