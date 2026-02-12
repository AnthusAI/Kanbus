Feature: Local issue listing
  As a Taskulus user
  I want list output to respect local issue filters
  So that I can focus on shared or personal work

  Scenario: List includes local issues by default
    Given a Taskulus project with default configuration
    And an issue "tsk-shared01" exists
    And a local issue "tsk-local01" exists
    When I run "tsk list"
    Then stdout should contain "tsk-shared01"
    And stdout should contain "tsk-local01"

  Scenario: List excludes local issues with --no-local
    Given a Taskulus project with default configuration
    And an issue "tsk-shared01" exists
    And a local issue "tsk-local01" exists
    When I run "tsk list --no-local"
    Then stdout should contain "tsk-shared01"
    And stdout should not contain "tsk-local01"

  Scenario: List shows only local issues with --local-only
    Given a Taskulus project with default configuration
    And an issue "tsk-shared01" exists
    And a local issue "tsk-local01" exists
    When I run "tsk list --local-only"
    Then stdout should contain "tsk-local01"
    And stdout should not contain "tsk-shared01"

  Scenario: Local listing ignores non-issue files
    Given a Taskulus project with default configuration
    And a local issue "tsk-local01" exists
    And a non-issue file exists in the local issues directory
    When I run "tsk list --local-only"
    Then stdout should contain "tsk-local01"

  Scenario: List rejects local-only conflicts
    Given a Taskulus project with default configuration
    When I run "tsk list --local-only --no-local"
    Then the command should fail with exit code 1
    And stderr should contain "local-only conflicts with no-local"
