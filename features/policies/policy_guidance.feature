Feature: Policy guidance hooks
  As a team using coding agents
  I want policy guardrails to provide in-the-moment guidance
  So that agents can follow process without repeatedly hitting blockers

  Scenario: Epic cannot enter ready or in_progress without at least one child issue
    Given a Kanbus project with default configuration
    And epic workflow allows transition from "open" to "ready"
    And epic workflow allows transition from "blocked" to "ready"
    And epic workflow allows transition from "open" to "in_progress"
    And epic workflow allows transition from "blocked" to "in_progress"
    And a policy file "epic-entry.policy" with content:
      """
      Feature: Epic entry guardrails

        Rule: Entry transitions require decomposition
          Scenario: Epic entering ready must have children
            Given the issue type is "epic"
            When transitioning to "ready"
            Then the issue must have at least 1 child issues

          Scenario: Epic entering in_progress must have children
            Given the issue type is "epic"
            When transitioning to "in_progress"
            Then the issue must have at least 1 child issues
      """
    And an issue "kanbus-epic01" of type "epic" with status "open"
    And an issue "kanbus-epic02" of type "epic" with status "blocked"
    And an issue "kanbus-epic03" of type "epic" with status "open"
    And an issue "kanbus-epic04" of type "epic" with status "blocked"
    When I run "kanbus update kanbus-epic01 --status ready"
    Then the command should fail with exit code 1
    And stderr should contain "issue has 0 child issue(s) but must have at least 1"
    And issue "kanbus-epic01" should have status "open"
    When I run "kanbus update kanbus-epic02 --status ready"
    Then the command should fail with exit code 1
    And stderr should contain "issue has 0 child issue(s) but must have at least 1"
    And issue "kanbus-epic02" should have status "blocked"
    When I run "kanbus update kanbus-epic03 --status in_progress"
    Then the command should fail with exit code 1
    And stderr should contain "issue has 0 child issue(s) but must have at least 1"
    And issue "kanbus-epic03" should have status "open"
    When I run "kanbus update kanbus-epic04 --status in_progress"
    Then the command should fail with exit code 1
    And stderr should contain "issue has 0 child issue(s) but must have at least 1"
    And issue "kanbus-epic04" should have status "blocked"

  Scenario: Epic can enter ready and in_progress when it has at least one child issue
    Given a Kanbus project with default configuration
    And epic workflow allows transition from "open" to "ready"
    And epic workflow allows transition from "open" to "in_progress"
    And a policy file "epic-entry.policy" with content:
      """
      Feature: Epic entry guardrails

        Rule: Entry transitions require decomposition
          Scenario: Epic entering ready must have children
            Given the issue type is "epic"
            When transitioning to "ready"
            Then the issue must have at least 1 child issues

          Scenario: Epic entering in_progress must have children
            Given the issue type is "epic"
            When transitioning to "in_progress"
            Then the issue must have at least 1 child issues
      """
    And an issue "kanbus-epic01" of type "epic" with status "open"
    And an issue "kanbus-task01" of type "task" with status "open" and parent "kanbus-epic01"
    And an issue "kanbus-epic02" of type "epic" with status "open"
    And an issue "kanbus-task02" of type "task" with status "open" and parent "kanbus-epic02"
    When I run "kanbus update kanbus-epic01 --status ready"
    Then the command should succeed
    And issue "kanbus-epic01" should have status "ready"
    When I run "kanbus update kanbus-epic02 --status in_progress"
    Then the command should succeed
    And issue "kanbus-epic02" should have status "in_progress"

  Scenario: Epic updates are blocked in ready or in_progress without children
    Given a Kanbus project with default configuration
    And a policy file "epic-entry-create.policy" with content:
      """
      Feature: Epic entry guardrails

        Rule: Active-state bypass prevention
          Scenario: Epic in ready must have children
            Given the issue type is "epic"
            Given the issue status is "ready"
            When updating an issue
            Then the issue must have at least 1 child issues

          Scenario: Epic in in_progress must have children
            Given the issue type is "epic"
            Given the issue status is "in_progress"
            When updating an issue
            Then the issue must have at least 1 child issues
      """
    And an issue "kanbus-epic-ready" of type "epic" with status "ready"
    And an issue "kanbus-epic-active" of type "epic" with status "in_progress"
    When I run "kanbus update kanbus-epic-ready --title Updated"
    Then the command should fail with exit code 1
    And stderr should contain "issue has 0 child issue(s) but must have at least 1"
    And issue "kanbus-epic-ready" should have title "Title"
    When I run "kanbus update kanbus-epic-active --title Updated"
    Then the command should fail with exit code 1
    And stderr should contain "issue has 0 child issue(s) but must have at least 1"
    And issue "kanbus-epic-active" should have title "Title"

  Scenario: Guidance hook runs after create for epic decomposition coaching
    Given a Kanbus project with default configuration
    And a policy file "epic-guidance.policy" with content:
      """
      Feature: Epic guidance

        Rule: Epic decomposition coaching
          Scenario: Epic creation reminder
            Given the issue type is "epic"
            When creating an issue
            Then warn "Create at least one child story or task before moving an epic to ready."
            Then explain "Epics represent milestones composed of multiple child issues."
            Then suggest "If this is a single deliverable, model it as a story or task instead of an epic."
      """
    When I run "kanbus create 'Plan launch' --type epic"
    Then the command should succeed
    And stderr should contain "GUIDANCE WARNING: Create at least one child story or task before moving an epic to ready."
    And stderr should contain "Explanation: Epics represent milestones composed of multiple child issues."
    And stderr should contain "GUIDANCE SUGGESTION: If this is a single deliverable, model it as a story or task instead of an epic."

  Scenario: Guidance hook runs after show
    Given a Kanbus project with default configuration
    And a policy file "view-guidance.policy" with content:
      """
      Feature: View guidance

        Rule: Viewing reminders
          Scenario: Viewing reminder
            When viewing an issue
            Then warn "Confirm the issue has the right owner before you start."
            Then suggest "If work started, move the issue to in_progress."
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus show kanbus-test01"
    Then the command should succeed
    And stderr should contain "GUIDANCE WARNING: Confirm the issue has the right owner before you start."
    And stderr should contain "GUIDANCE SUGGESTION: If work started, move the issue to in_progress."

  Scenario: Guidance hooks run on every list and ready call
    Given a Kanbus project with default configuration
    And a policy file "list-guidance.policy" with content:
      """
      Feature: List guidance

        Rule: List reminders
          Scenario: List reminder
            When listing issues
            Then suggest "Remember to reflect your current status in issue states as you work."

          Scenario: Ready reminder
            When listing ready issues
            Then warn "Ready means unblocked and actionable now."
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus list"
    Then the command should succeed
    And stderr should contain "GUIDANCE SUGGESTION: Remember to reflect your current status in issue states as you work."
    When I run "kanbus list"
    Then the command should succeed
    And stderr should contain "GUIDANCE SUGGESTION: Remember to reflect your current status in issue states as you work."
    When I run "kanbus ready"
    Then the command should succeed
    And stderr should contain "GUIDANCE WARNING: Ready means unblocked and actionable now."

  Scenario: Global no-guidance flag suppresses guidance output
    Given a Kanbus project with default configuration
    And a policy file "view-guidance.policy" with content:
      """
      Feature: View guidance

        Rule: Viewing reminders
          Scenario: Viewing reminder
            When viewing an issue
            Then suggest "Keep statuses updated as you work."
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus --no-guidance show kanbus-test01"
    Then the command should succeed
    And stderr should not contain "GUIDANCE SUGGESTION"

  Scenario: Orphan explain step fails policy validation
    Given a Kanbus project with default configuration
    And a policy file "invalid-explain.policy" with content:
      """
      Feature: Invalid explain

        Rule: Structural validation
          Scenario: Explain without prior emitted step
            Then explain "This explain has no parent item."
      """
    When I run "kanbus policy validate"
    Then the command should fail with exit code 1
    And stderr should contain "orphan explain step"

  Scenario: Policy guide command emits guidance for an issue
    Given a Kanbus project with default configuration
    And a policy file "view-guidance.policy" with content:
      """
      Feature: View guidance

        Rule: Viewing reminders
          Scenario: Viewing reminder
            When viewing an issue
            Then warn "Review parent-child structure before making workflow changes."
            Then suggest "Use update to keep status aligned with current progress."
      """
    And an issue "kanbus-test01" of type "task" with status "open"
    When I run "kanbus policy guide kanbus-test01"
    Then the command should succeed
    And stderr should contain "GUIDANCE WARNING: Review parent-child structure before making workflow changes."
    And stderr should contain "GUIDANCE SUGGESTION: Use update to keep status aligned with current progress."
