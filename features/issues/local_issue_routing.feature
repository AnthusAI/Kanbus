Feature: Local issue routing

  Scenario: Create a local issue
    Given a Taskulus project with default configuration
    When I run "tsk create --local Local task"
    Then the command should succeed
    And a local issue file should be created in the local issues directory
    And .gitignore should include "project-local/"

  Scenario: Promote a local issue to shared
    Given a Taskulus project with default configuration
    And a local issue "tsk-local01" exists
    When I run "tsk promote tsk-local01"
    Then the command should succeed
    And issue "tsk-local01" should exist in the shared issues directory
    And issue "tsk-local01" should not exist in the local issues directory

  Scenario: Localize a shared issue
    Given a Taskulus project with default configuration
    And an issue "tsk-shared01" exists
    When I run "tsk localize tsk-shared01"
    Then the command should succeed
    And issue "tsk-shared01" should exist in the local issues directory
    And issue "tsk-shared01" should not exist in the shared issues directory
    And .gitignore should include "project-local/"

  Scenario: Promote fails when project-local is missing
    Given a Taskulus project with default configuration
    When I run "tsk promote tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "project-local not initialized"

  Scenario: Promote fails when local issue is missing
    Given a Taskulus project with default configuration
    And a local issue "tsk-other" exists
    When I run "tsk promote tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Promote fails when shared issue already exists
    Given a Taskulus project with default configuration
    And a local issue "tsk-dupe01" exists
    And an issue "tsk-dupe01" exists
    When I run "tsk promote tsk-dupe01"
    Then the command should fail with exit code 1
    And stderr should contain "already exists"

  Scenario: Localize fails when local issue already exists
    Given a Taskulus project with default configuration
    And a local issue "tsk-dupe02" exists
    And an issue "tsk-dupe02" exists
    When I run "tsk localize tsk-dupe02"
    Then the command should fail with exit code 1
    And stderr should contain "already exists"

  Scenario: Localize fails when shared issue is missing
    Given a Taskulus project with default configuration
    When I run "tsk localize tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Promote fails without a project
    Given an empty git repository
    When I run "tsk promote tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Localize fails without a project
    Given an empty git repository
    When I run "tsk localize tsk-missing"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Local creation preserves existing gitignore entry
    Given a Taskulus project with default configuration
    And .gitignore already includes "project-local/"
    When I run "tsk create --local Local task"
    Then the command should succeed
    And .gitignore should include "project-local/" only once

  Scenario: Local creation appends gitignore with newline
    Given a Taskulus project with default configuration
    And a .gitignore without a trailing newline exists
    When I run "tsk create --local Local task"
    Then the command should succeed
    And .gitignore should include "project-local/"
