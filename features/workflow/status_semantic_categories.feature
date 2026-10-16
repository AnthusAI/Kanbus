Feature: Status semantic categories

  Scenario: Claiming resolves the in_progress semantic category to a custom status key
    Given a Kanbus project with default configuration
    And the primary in_progress status key is configured as "doing"
    And an issue "kanbus-test01" of type "task" with status "open"
    And the current user is "dev@example.com"
    When I run "kanbus update kanbus-test01 --claim"
    Then issue "kanbus-test01" should have status "doing"
    And issue "kanbus-test01" should have assignee "dev@example.com"

  Scenario: A configuration that predates semantic categories still loads
    Given a Kanbus project with default configuration
    And the configuration omits every semantic category and adds the status "published"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "published" should have semantic category "done"
    And the configured status "open" should have semantic category "todo"
    And the configured status "in_progress" should have semantic category "in_progress"
    And the configured status "closed" should have semantic category "done"

  Scenario: A custom stage without a semantic category is treated as in progress
    Given a Kanbus project with default configuration
    And the configuration omits every semantic category and adds the status "copywriting"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "copywriting" should have semantic category "in_progress"

  Scenario: An explicit semantic category is never overridden by the derived one
    Given a Kanbus project with default configuration
    And the configuration adds the status "published" with semantic category "todo"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "published" should have semantic category "todo"

  @wip
  Scenario Outline: A status without a semantic category derives in_review or blocked from any word of its key or name
    Given a Kanbus project with default configuration
    And the configuration omits every semantic category and adds the status "<key>" named "<name>"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "<key>" should have semantic category "<category>"

    Examples:
      | key              | name             | category  |
      | review           | Review           | in_review |
      | awaiting-review  | Awaiting sign-off| in_review |
      | qa               | In Review        | in_review |
      | blocked          | Blocked          | blocked   |
      | waiting          | Blocked on legal | blocked   |
      | Peer_Review      | Peer             | in_review |

  @wip
  Scenario: Derivation checks done, then blocked, then review, then todo words
    Given a Kanbus project with default configuration
    And the configuration omits every semantic category and adds the status "ready_for_review" named "Ready for review"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "ready_for_review" should have semantic category "in_review"

  @wip
  Scenario: A configuration that predates semantic categories derives review and blocked as their own categories
    Given a Kanbus project with default configuration
    And the configuration omits every semantic category and adds the status "published"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "review" should have semantic category "in_review"
    And the configured status "blocked" should have semantic category "blocked"

  @wip
  Scenario Outline: The canonical semantic categories include review and blocked
    Given a Kanbus project with default configuration
    And the configuration adds the status "<key>" with semantic category "<category>"
    When I run "kanbus list"
    Then the command should succeed
    And the configured status "<key>" should have semantic category "<category>"

    Examples:
      | key       | category    |
      | qa_review | in_review   |
      | on_hold   | blocked     |
      | doing     | in_progress |
      | shipped   | done        |
      | triage    | todo        |

  @wip
  Scenario: An unsupported semantic category is rejected
    Given a Kanbus project with default configuration
    And the configuration adds the status "archived" with semantic category "archived"
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should equal "error: statuses.archived.semantic_category \"archived\" is unsupported; expected one of todo, in_progress, in_review, blocked, done\n"
