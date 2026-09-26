@console @slow @kbs-217bf8
Feature: Console board horizontal scroll stability
  As a Kanbus user
  I want the board to stay where I scrolled it
  So that background updates never move the columns I am looking at

  Scenario: A realtime issue move does not shift the board horizontally
    Given the console is open
    And the browser viewport is 500 by 800
    And the console has only these issues:
      | id         | title        | status  |
      | kbs-scroll | Scroll issue | open    |
      | kbs-other  | Other issue  | backlog |
      | kbs-copy   | Copy issue   | copy_writing |
      | kbs-doing  | Doing issue  | in_progress |
      | kbs-stuck  | Stuck issue  | blocked |
    When I switch to the "Tasks" tab
    And I scroll the board to the right
    And I record the board horizontal scroll position
    And the issue "kbs-scroll" is moved to "in_progress" by a realtime update
    Then the board horizontal scroll position should never have changed
