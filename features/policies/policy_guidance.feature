Feature: Policy guidance hooks
  As a team using coding agents
  I want policy guardrails to provide in-the-moment guidance
  So that agents can follow process without repeatedly hitting blockers

  Scenario: Epic cannot move to ready without at least one child issue
    Given a Kanbus project with default configuration
    And epic workflow allows transition from "open" to "ready"
    And a policy file "epic-ready.policy" with content:
      """
      Feature: Epic readiness guardrail

        Scenario: Epic needs child issues before ready
          Given the issue type is "epic"
          When transitioning to "ready"
          Then the issue must have at least 1 child issues
          Then explain "Epics represent milestones composed of multiple child issues."
          Then warn "Create at least one child story or task before marking an epic ready."
          Then explain "If this is a single deliverable, model it as a story or task instead of an epic."
          Then suggest "Break the milestone into child issues and then move the epic to ready."
      """
    And an issue "kanbus-epic01" of type "epic" with status "open"
    When I run "kanbus update kanbus-epic01 --status ready"
    Then the command should fail with exit code 1
    And stderr should contain "issue has 0 child issue(s) but must have at least 1"
    And stderr should contain "Explanation: Epics represent milestones composed of multiple child issues."
    And stderr should contain "GUIDANCE WARNING: Create at least one child story or task before marking an epic ready."
    And stderr should contain "Explanation: If this is a single deliverable, model it as a story or task instead of an epic."
    And stderr should contain "GUIDANCE SUGGESTION: Break the milestone into child issues and then move the epic to ready."
    And issue "kanbus-epic01" should have status "open"

  Scenario: Epic can move to ready when it has at least one child issue
    Given a Kanbus project with default configuration
    And epic workflow allows transition from "open" to "ready"
    And a policy file "epic-ready.policy" with content:
      """
      Feature: Epic readiness guardrail

        Scenario: Epic needs child issues before ready
          Given the issue type is "epic"
          When transitioning to "ready"
          Then the issue must have at least 1 child issues
      """
    And an issue "kanbus-epic01" of type "epic" with status "open"
    And an issue "kanbus-task01" of type "task" with status "open" and parent "kanbus-epic01"
    When I run "kanbus update kanbus-epic01 --status ready"
    Then the command should succeed
    And issue "kanbus-epic01" should have status "ready"

  Scenario: Guidance hook runs after show
    Given a Kanbus project with default configuration
    And a policy file "view-guidance.policy" with content:
      """
      Feature: View guidance

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
