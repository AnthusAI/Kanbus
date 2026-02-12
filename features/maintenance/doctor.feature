Feature: Doctor diagnostics
  As a Taskulus maintainer
  I want a doctor command that validates the environment
  So that setup issues are visible quickly

  Scenario: Doctor succeeds with a valid project
    Given a Taskulus project with default configuration
    When I run "tsk doctor"
    Then the command should succeed
    And stdout should contain "ok"

  Scenario: Doctor fails without a project
    Given an empty git repository
    When I run "tsk doctor"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Doctor fails without a git repository
    Given a directory that is not a git repository
    When I run "tsk doctor"
    Then the command should fail with exit code 1
    And stderr should contain "not a git repository"

  Scenario: Doctor fails with invalid configuration
    Given a Taskulus project with an invalid configuration containing unknown fields
    When I run "tsk doctor"
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"
