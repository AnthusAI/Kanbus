Feature: Project utility helpers
  As a Taskulus maintainer
  I want project discovery helpers to handle edge cases
  So that project resolution is predictable

  Scenario: Discover a single project directory under the root
    Given a repository with a single project directory
    When project directories are discovered
    Then exactly one project directory should be returned

  Scenario: Loading a project fails when none exist
    Given an empty repository without a project directory
    When the project directory is loaded
    Then project discovery should fail with "project not initialized"

  Scenario: Loading a project fails when multiple projects exist
    Given a repository with multiple project directories
    When the project directory is loaded
    Then project discovery should fail with "multiple projects found"

  Scenario: Dotfile paths must exist
    Given a repository with a .taskulus file referencing a missing path
    When project directories are discovered
    Then project discovery should fail with "taskulus path not found"

  Scenario: Dotfile paths may include blank lines
    Given a repository with a .taskulus file referencing a valid path with blank lines
    When project directories are discovered
    Then project discovery should include the referenced path

  Scenario: Project discovery without git finds no dotfile paths
    Given a non-git directory without projects
    When project directories are discovered
    Then project discovery should return no projects

  Scenario: Git root must point to a directory
    Given a repository with a fake git root pointing to a file
    When project directories are discovered
    Then project discovery should return no projects

  Scenario: Dotfile search stops at filesystem root
    When taskulus dotfile paths are discovered from the filesystem root
    Then project discovery should return no projects
