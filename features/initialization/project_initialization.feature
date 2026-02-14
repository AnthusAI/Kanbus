Feature: Project initialization
  As a developer starting a new project
  I want to initialize a Taskulus project directory
  So that I can begin tracking issues alongside my code

  Scenario: Initialize with default settings
    Given an empty git repository
    When I run "tsk init"
    Then a "project" directory should exist
    And a "project/issues" directory should exist and be empty
    And a "project/wiki" directory should not exist
    And a ".taskulus.yml" file should be created
    And a "CONTRIBUTING_AGENT.template.md" file should be created
    And CONTRIBUTING_AGENT.template.md should contain "This is The Way."
    And CONTRIBUTING_AGENT.template.md should contain "As a <role>, I want <capability>, so that <benefit>."
    And project/AGENTS.md should be created with the warning
    And project/DO_NOT_EDIT should be created with the warning

  Scenario: Initialize with a project-local directory
    Given an empty git repository
    When I run "tsk init --local"
    Then a "project" directory should exist
    And a "project/issues" directory should exist and be empty
    And a "project-local/issues" directory should exist
    And .gitignore should include "project-local/"
    And a "CONTRIBUTING_AGENT.template.md" file should be created
    And CONTRIBUTING_AGENT.template.md should contain "This is The Way."

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
