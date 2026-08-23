Feature: CLI argument parsing and edge cases
  Scenario: Interactive project repair prompt is triggered for read commands
    Given an empty git repository
    And I run "kanbus init"
    And I remove the directory "project/issues"
    And I remove the directory "project/events"
    And the environment variable "KANBUS_FORCE_INTERACTIVE" is set to "1"
    When I run "kanbus list" and respond "y"
    Then the command should succeed
    And stderr should contain "Project structure repaired."
    And the directory "project/issues" should exist

  Scenario: Project structure check is skipped for setup commands
    Given an empty git repository
    And the directory "project" exists
    And a file ".kanbus.yml" with content:
      """
      project_key: kanbus
      """
    When I run "kanbus setup agents"
    Then the command should succeed
    And the directory "project/issues" should not exist

  Scenario: KANBUS_FORCE_INTERACTIVE enables interactive delete prompt without tty
    Given a Kanbus project with default configuration
    And an issue "kanbus-test01" of type "task" with status "open"
    And the environment variable "KANBUS_FORCE_INTERACTIVE" is set to "1"
    When I run "kanbus delete kanbus-test01" and respond "y"
    Then the command should succeed
    And stdout should contain "Deleted kanbus-test01"

  Scenario: Explicit --beads flag overrides automatic project detection
    Given an empty git repository
    And the directory ".beads/issues" exists
    And a beads issue "kanbus-abc" exists
    When I run "kanbus --beads list"
    Then the command should succeed
    And stdout should contain "kanbus-abc"
