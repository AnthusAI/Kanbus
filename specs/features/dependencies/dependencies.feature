@wip
Feature: Issue dependencies
  As a Taskulus user
  I want to manage dependencies between issues
  So that blocked work is tracked and cycles are prevented

  @wip
  Scenario: Add a blocked-by dependency
    Given a Taskulus project with default configuration
    And issues "tsk-parent" and "tsk-child" exist
    When I run "tsk dep add tsk-child --blocked-by tsk-parent"
    Then the command should succeed
    And issue "tsk-child" should depend on "tsk-parent" with type "blocked-by"

  @wip
  Scenario: Add a relates-to dependency
    Given a Taskulus project with default configuration
    And issues "tsk-left" and "tsk-right" exist
    When I run "tsk dep add tsk-left --relates-to tsk-right"
    Then the command should succeed
    And issue "tsk-left" should depend on "tsk-right" with type "relates-to"

  @wip
  Scenario: Remove a dependency
    Given a Taskulus project with default configuration
    And issues "tsk-left" and "tsk-right" exist
    And issue "tsk-left" depends on "tsk-right" with type "blocked-by"
    When I run "tsk dep remove tsk-left --blocked-by tsk-right"
    Then the command should succeed
    And issue "tsk-left" should not depend on "tsk-right" with type "blocked-by"

  @wip
  Scenario: Reject dependency cycles
    Given a Taskulus project with default configuration
    And issues "tsk-a" and "tsk-b" exist
    And issue "tsk-a" depends on "tsk-b" with type "blocked-by"
    When I run "tsk dep add tsk-b --blocked-by tsk-a"
    Then the command should fail with exit code 1
    And stderr should contain "cycle detected"

  @wip
  Scenario: Ready query excludes blocked issues
    Given a Taskulus project with default configuration
    And issues "tsk-ready" and "tsk-blocked" exist
    And issue "tsk-blocked" depends on "tsk-ready" with type "blocked-by"
    When I run "tsk ready"
    Then stdout should contain "tsk-ready"
    And stdout should not contain "tsk-blocked"
