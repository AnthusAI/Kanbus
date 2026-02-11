@wip
Feature: Project initialization
  As a developer starting a new project
  I want to initialize a Taskulus project directory
  So that I can begin tracking issues alongside my code

  @wip
  Scenario: Initialize with default settings
    Given an empty git repository
    When I run "tsk init"
    Then a ".taskulus.yaml" file should exist in the repository root
    And a "project" directory should exist
    And a "project/config.yaml" file should exist with default configuration
    And a "project/issues" directory should exist and be empty
    And a "project/wiki" directory should exist
    And a "project/wiki/index.md" file should exist
    And a "project/.cache" directory should not exist yet

  @wip
  Scenario: Initialize with custom directory name
    Given an empty git repository
    When I run "tsk init --dir tracking"
    Then a ".taskulus.yaml" file should exist pointing to "tracking"
    And a "tracking" directory should exist
    And a "tracking/config.yaml" file should exist with default configuration

  @wip
  Scenario: Refuse to initialize when project already exists
    Given a git repository with an existing Taskulus project
    When I run "tsk init"
    Then the command should fail with exit code 1
    And stderr should contain "already initialized"

  @wip
  Scenario: Refuse to initialize outside a git repository
    Given a directory that is not a git repository
    When I run "tsk init"
    Then the command should fail with exit code 1
    And stderr should contain "not a git repository"
