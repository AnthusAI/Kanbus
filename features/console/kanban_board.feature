@console
Feature: Console kanban board
  As a Kanbus user
  I want a realtime kanban console for issues
  So that I can track work visually

  Scenario: Default view shows epics when no preference is stored
    Given the console is open
    And local storage is cleared
    When the console is reloaded
    Then the "Epics" tab should be selected
    And I should see the issue "Observability overhaul"
    And I should not see the issue "Increase reliability"

  Scenario: Initiatives tab shows initiative issues
    Given the console is open
    When I switch to the "Initiatives" tab
    Then I should see the issue "Increase reliability"

  Scenario: Tasks tab shows task level issues
    Given the console is open
    When I switch to the "Tasks" tab
    Then I should see the issue "Add structured logging"
    And I should see the issue "Fix crash on startup"
    And I should not see the issue "Wire logger middleware"

  Scenario: Task detail shows sub-tasks
    Given the console is open
    When I switch to the "Tasks" tab
    And I open the task "Add structured logging"
    Then I should see the sub-task "Wire logger middleware"

  Scenario: Realtime updates surface new tasks
    Given the console is open
    When I switch to the "Tasks" tab
    And a new task issue named "Ship trace headers" is added
    Then I should see the issue "Ship trace headers"

  Scenario: View mode preference is remembered
    Given the console is open
    When I switch to the "Tasks" tab
    And the console is reloaded
    Then the "Tasks" tab should be selected

  Scenario: Non-done columns default to FIFO ordering
    Given the console is open
    And no issues exist in the console
    And the Kanbus configuration has no sort_order rules
    And the console has only these issues:
      | id                | title                | status      | priority | created_at               | updated_at               |
      | kanbus-backlog-1  | Backlog early        | backlog     | 2        | 2026-01-01T00:00:00.000Z | 2026-01-04T00:00:00.000Z |
      | kanbus-backlog-2  | Backlog late         | backlog     | 2        | 2026-01-02T00:00:00.000Z | 2026-01-03T00:00:00.000Z |
      | kanbus-open-1     | Discovery early      | open        | 2        | 2026-01-01T00:00:00.000Z | 2026-01-04T00:00:00.000Z |
      | kanbus-open-2     | Discovery late       | open        | 2        | 2026-01-02T00:00:00.000Z | 2026-01-03T00:00:00.000Z |
      | kanbus-progress-1 | Progress early       | in_progress | 2        | 2026-01-01T00:00:00.000Z | 2026-01-04T00:00:00.000Z |
      | kanbus-progress-2 | Progress late        | in_progress | 2        | 2026-01-02T00:00:00.000Z | 2026-01-03T00:00:00.000Z |
      | kanbus-blocked-1  | Blocked early        | blocked     | 2        | 2026-01-01T00:00:00.000Z | 2026-01-04T00:00:00.000Z |
      | kanbus-blocked-2  | Blocked late         | blocked     | 2        | 2026-01-02T00:00:00.000Z | 2026-01-03T00:00:00.000Z |
    When I switch to the "Tasks" tab
    Then the "backlog" column should list issues in order "Backlog early, Backlog late"
    And the "open" column should list issues in order "Discovery early, Discovery late"
    And the "in_progress" column should list issues in order "Progress early, Progress late"
    And the "blocked" column should list issues in order "Blocked early, Blocked late"

  Scenario: Done column always sorts by recent updates
    Given the console is open
    And no issues exist in the console
    And the Kanbus configuration sets sort_order for category "Done" to preset "fifo"
    And the Kanbus configuration sets sort_order for status "closed" to preset "fifo"
    And the console has only these issues:
      | id               | title       | status | priority | created_at               | updated_at               |
      | kanbus-done-old  | Done older  | closed | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
      | kanbus-done-new  | Done newer  | closed | 2        | 2026-01-03T00:00:00.000Z | 2026-01-05T00:00:00.000Z |
    When I switch to the "Tasks" tab
    Then the "closed" column should list issues in order "Done newer, Done older"

  Scenario: Category-level sort_order applies when status-level is absent
    Given the console is open
    And no issues exist in the console
    And the Kanbus configuration sets sort_order for category "To do" to preset "recently-updated"
    And the console has only these issues:
      | id             | title            | status | priority | created_at               | updated_at               |
      | kanbus-open-a  | Discovery first  | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
      | kanbus-open-b  | Discovery second | open   | 2        | 2026-01-02T00:00:00.000Z | 2026-01-04T00:00:00.000Z |
    When I switch to the "Tasks" tab
    Then the "open" column should list issues in order "Discovery second, Discovery first"

  Scenario: Status-level sort_order overrides category-level rule
    Given the console is open
    And no issues exist in the console
    And the Kanbus configuration sets sort_order for category "To do" to preset "recently-updated"
    And the Kanbus configuration sets sort_order for status "open" to preset "fifo"
    And the console has only these issues:
      | id             | title            | status | priority | created_at               | updated_at               |
      | kanbus-open-a  | Discovery first  | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
      | kanbus-open-b  | Discovery second | open   | 2        | 2026-01-02T00:00:00.000Z | 2026-01-04T00:00:00.000Z |
    When I switch to the "Tasks" tab
    Then the "open" column should list issues in order "Discovery first, Discovery second"

  Scenario: Raw status sort_order applies priority then created_at
    Given the console is open
    And no issues exist in the console
    And the Kanbus configuration sets raw sort_order for status "open" to "priority asc, created_at asc"
    And the console has only these issues:
      | id             | title           | status | priority | created_at               | updated_at               |
      | kanbus-open-p2 | Priority 2      | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-05T00:00:00.000Z |
      | kanbus-open-p1 | Priority 1 late | open   | 1        | 2026-01-03T00:00:00.000Z | 2026-01-04T00:00:00.000Z |
      | kanbus-open-p0 | Priority 1      | open   | 1        | 2026-01-02T00:00:00.000Z | 2026-01-03T00:00:00.000Z |
    When I switch to the "Tasks" tab
    Then the "open" column should list issues in order "Priority 1, Priority 1 late, Priority 2"
