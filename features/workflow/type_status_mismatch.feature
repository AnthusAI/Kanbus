Feature: Type and status workflow mismatch remediation
  As a Kanbus agent or maintainer
  I want actionable remediation hints when an issue type and status disagree
  So that I can fix mismatches without hand-editing issue JSON

  Scenario: Validate reports story at open with move and status hints
    Given a Kanbus project with an editorial story workflow configuration
    And an issue "kanbus-story01" of type "story" with status "open"
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "kanbus-story01"
    And stderr should contain "type 'story'"
    And stderr should contain "status 'open'"
    And stderr should contain "allowed:"
    And stderr should contain "kbs move kanbus-story01 task"
    And stderr should contain "kbs update kanbus-story01 --status"

  Scenario: Doctor reports story at open with the same remediation hints
    Given a Kanbus project with an editorial story workflow configuration
    And an issue "kanbus-story01" of type "story" with status "open"
    When I run "kanbus doctor"
    Then the command should fail with exit code 1
    And stderr should contain "kanbus-story01"
    And stderr should contain "kbs move kanbus-story01 task"
    And stderr should contain "kbs update kanbus-story01 --status"

  Scenario: Creating a story fails when initial status is outside the story workflow
    Given a Kanbus project with an editorial story workflow configuration
    When I run "kanbus create \"Editorial story\" --type story"
    Then the command should fail with exit code 1
    And stderr should contain "type 'story'"
    And stderr should contain "status 'open'"
    And stderr should contain "use --type task"
