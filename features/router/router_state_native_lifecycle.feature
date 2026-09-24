Feature: State-native Issue Router lifecycle
  As a Kanbus maintainer
  I want the router lifecycle to follow the router-marked status of each semantic category
  So that Kanbus statuses are the single source of truth and the router has no second status map

  Background:
    Given a Kanbus project with router configuration:
      """
      router:
        limits:
          project_wip: 2
          review_wip: 1
        forge:
          repository: anthusai/kanbus
        providers:
          codex-default:
            adapter: codex
        classes:
          implementation:
            providers: [codex-default]
      """
    And the project configuration includes:
      """
      workflows:
        default:
          backlog: [open, closed]
          open: [in_progress, closed, backlog]
          Discovery: [in_progress, open, backlog]
          in_progress: [open, review, blocked, closed, backlog]
          review: [in_progress, closed]
          blocked: [in_progress, closed, backlog]
          closed: [open, backlog]
      transition_labels:
        default:
          backlog:
            open: Start discovery
            closed: Drop
          open:
            in_progress: Start work
            closed: Drop
            backlog: Back to backlog
          Discovery:
            in_progress: Claim
            open: Start work
            backlog: Back to backlog
          in_progress:
            open: Pause
            review: Ready for review
            blocked: Block
            closed: Complete
            backlog: Back to backlog
          review:
            in_progress: Request changes
            closed: Approve and close
          blocked:
            in_progress: Unblock
            closed: Drop
            backlog: Back to backlog
          closed:
            open: Reopen
            backlog: Back to backlog
      statuses:
        - key: backlog
          name: Backlog
          category: To do
          semantic_category: todo
        - key: open
          name: Ready
          category: To do
          semantic_category: todo
        - key: Discovery
          name: Discovery
          category: To do
          semantic_category: todo
          router: true
        - key: in_progress
          name: In progress
          category: In progress
          semantic_category: in_progress
          router: true
        - key: review
          name: Review
          category: In progress
          semantic_category: in_review
          router: true
        - key: blocked
          name: Blocked
          category: In progress
          semantic_category: blocked
          router: true
        - key: closed
          name: Done
          category: Done
          semantic_category: done
          router: true
      """

  Scenario: Router-marked statuses replace the router workflow map
    When the router configuration is loaded
    Then the configuration should be valid

  Scenario: The router workflow map is rejected after migration
    Given a Kanbus project with router configuration field "workflow"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.workflow is an unknown field\n"

  Scenario Outline: A status semantic category must be one of the five canonical categories
    Given status "review" has semantic_category "<category>"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: statuses.review.semantic_category \"<category>\" must be one of todo, in_progress, in_review, blocked, done\n"

    Examples:
      | category |
      | waiting  |
      | review   |
      | complete |

  Scenario Outline: An enabled router requires one marked status for every semantic category
    Given status "<status>" has router marker "false"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router requires one router: true status for semantic_category \"<category>\"\n"

    Examples:
      | status      | category    |
      | Discovery   | todo        |
      | in_progress | in_progress |
      | review      | in_review   |
      | blocked     | blocked     |
      | closed      | done        |

  Scenario: A semantic category cannot have two router-marked statuses
    Given status "qa" is defined as "QA" with semantic_category "in_review" and router marker "true"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router status marker for semantic_category \"in_review\" is used by both \"review\" and \"qa\"\n"

  Scenario: A project without a router does not need router markers
    Given a Kanbus project without a router configuration
    And status "review" has router marker "false"
    Then running "kanbus list" in the same project should succeed

  Scenario Outline: The configured workflow must allow every router lifecycle transition
    Given workflow "default" does not allow "<from>" to "<to>"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: workflow \"default\" does not allow router transition from \"<from>\" to \"<to>\"\n"

    Examples:
      | from        | to          |
      | Discovery   | in_progress |
      | in_progress | review      |
      | in_progress | blocked     |
      | review      | closed      |

  Scenario: Only the marked todo status is router intake
    Given routed package "kbs-401" is in status "Discovery"
    And routed package "kbs-402" is in status "open"
    When I run "kanbus router plan --json"
    Then eligible package order should be "kbs-401"

  Scenario: A Ready issue that opted into the router is not dispatched
    Given routed package "kbs-402" is in status "open"
    When I run "kanbus router plan --json"
    Then no package should be eligible

  Scenario: A claimed issue moves directly from Discovery to In Progress
    Given routed package "kbs-401" is in status "Discovery"
    And the fake adapter returns outcome "retryable_failure" for attempt 1
    When I run "kanbus router run --once"
    Then the command should fail with exit code 1
    And package "kbs-401" should transition to status "in_progress"

  Scenario: Successful agent work moves to the marked in-review status and stays there
    Given routed package "kbs-401" is in status "Discovery"
    And provider profile "codex-default" runs fake adapter outcome "completed"
    When I run "kanbus router run --once"
    Then the command should succeed
    And package "kbs-401" should be in status "review"

  Scenario: A blocked agent outcome moves to the marked blocked status
    Given routed package "kbs-401" is in status "Discovery"
    And provider profile "codex-default" runs fake adapter outcome "blocked"
    When I run "kanbus router run --once"
    Then package "kbs-401" should transition to status "blocked"

  Scenario: Marked statuses are used even when another status shares the category
    Given status "qa" is defined as "QA" with semantic_category "in_review" and router marker "false"
    And status "review" has router marker "false"
    And status "qa" has router marker "true"
    And workflow "default" allows "in_progress" to "qa"
    And workflow "default" allows "qa" to "closed"
    And routed package "kbs-401" is in status "Discovery"
    And provider profile "codex-default" runs fake adapter outcome "completed"
    When I run "kanbus router run --once"
    Then the command should succeed
    And package "kbs-401" should be in status "qa"
