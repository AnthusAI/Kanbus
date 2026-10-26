Feature: Issue Router process hygiene and watch resilience
  As an operator
  I want router adapters to be fully terminated and the watch loop to survive transient failures
  So that cancelled work never holds a worktree and a GitHub hiccup never stops the router

  Scenario: Terminating an adapter that forked a sleeping grandchild leaves no survivors
    Given a router adapter process that forked a sleeping grandchild
    When the router terminates the adapter process tree
    Then the adapter process should be reaped
    And the grandchild process should no longer be running

  Scenario Outline: A GitHub polling failure during watch is retried or stops the watch
    Given the router watch interval is <interval> seconds
    When GitHub pull request polling fails with <failure> for consecutive failure <count>
    Then the router watch should <outcome>

    Examples:
      | interval | failure             | count | outcome                |
      | 30       | HTTP status 500     | 1     | retry after 60 seconds |
      | 30       | HTTP status 500     | 3     | retry after 240 seconds |
      | 30       | HTTP status 500     | 9     | retry after 300 seconds |
      | 30       | HTTP status 429     | 1     | retry after 60 seconds |
      | 30       | a network error     | 2     | retry after 120 seconds |
      | 30       | HTTP status 401     | 1     | stop                   |

  Scenario: A recorded adapter whose process ID was reused is never signalled
    Given a recorded active adapter whose process ID now belongs to an unrelated process
    When the router signals the registered adapter for its package claim
    Then the unrelated process should still be running

  Scenario: A recorded adapter with a matching process identity is signalled
    Given a recorded active adapter whose process identity matches
    When the router signals the registered adapter for its package claim
    Then the recorded adapter process should have been terminated
