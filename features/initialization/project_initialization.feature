Feature: Project initialization
  As a developer starting a new project
  I want to initialize a Taskulus project directory
  So that I can begin tracking issues alongside my code

  Scenario: Initialize with default settings
    Given an empty git repository
    When I run "tsk init"
    Then a "project" directory should exist
    And a "project/issues" directory should exist and be empty
    And a "project/config.yaml" file should not exist
    And a "project/wiki" directory should not exist
    And a ".taskulus.yaml" file should not exist

  Scenario: Initialize with a project-local directory
    Given an empty git repository
    When I run "tsk init --local"
    Then a "project" directory should exist
    And a "project/issues" directory should exist and be empty
    And a "project-local/issues" directory should exist
    And .gitignore should include "project-local/"

  Scenario: Refuse to initialize when project already exists
    Given a git repository with an existing Taskulus project
    When I run "tsk init"
    Then the command should fail with exit code 1
    And stderr should contain "already initialized"

  Scenario: Refuse to initialize outside a git repository
    Given a directory that is not a git repository
    When I run "tsk init"
    Then the command should fail with exit code 1
    And stderr should contain "not a git repository"

  Scenario: Refuse to initialize inside the git metadata directory
    Given a git repository metadata directory
    When I run "tsk init"
    Then the command should fail with exit code 1
    And stderr should contain "not a git repository"
