@console @slow @kbs-15ffe1
Feature: Console conversation event details
  As a Kanbus user
  I want the agent's summary and run metadata in the issue event history
  So that I can see what an agent run said and where its work lives

  Scenario: Event history renders the agent message and run metadata from the events API
    Given the console is open
    And the console has only these issues:
      | id          | title        | status      |
      | kbs-convo   | Convo issue  | in_progress |
    And the issue "kbs-convo" has an agent conversation event with message "Finished the parser change" claim "claim-7" revision 3 and worktree "/work/kbs-convo-r3"
    When I switch to the "Tasks" tab
    And I open the task "Convo issue"
    And I open the issue event history
    Then the conversation event should show the message "Finished the parser change"
    And the conversation event should show claim "Claim: claim-7 · revision 3"
    And the conversation event should show worktree "Worktree: /work/kbs-convo-r3"
