Feature: Bounded board rendering
  A board column renders only the cards near its scroll position, so a column with
  hundreds of issues stays fast and a single record change re-renders only the affected card.

  Scenario: A column with 500 issues renders a bounded number of cards and scrolls to the last card
    Given a host application with article and task issues
    When the host renders a column of 500 issues
    Then the column header shows the count 500
    And at most 40 issue cards are rendered
    When I scroll the column to its end
    Then the issue card "bulk-500" is displayed
    And at most 40 issue cards are rendered

  Scenario: A collapsed column renders no cards
    Given a host application with article and task issues
    When the host renders a column of 500 issues
    And I collapse column "Open" with the keyboard
    Then column "Open" is collapsed
    And at most 0 issue cards are rendered

  Scenario: The selected card stays rendered while the column scrolls away from it
    Given a host application with article and task issues
    When the host renders a column of 500 issues
    And I select the issue card "bulk-3" with the keyboard
    And I scroll the column to its end
    Then the issue card "bulk-3" is displayed

  Scenario: Changing one issue re-renders only that card even when every record is a new object
    Given a host application with article and task issues
    When the host renders a column of 500 issues
    And the host replaces every issue with a copy and retitles issue "bulk-2" as "Retitled"
    Then the issue card "bulk-2" is rendered again with the title "Retitled"
    And no other issue card is rendered again
