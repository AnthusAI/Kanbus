Feature: Project utility helpers
  As a Kanbus maintainer
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

  Scenario: Loading a project tolerates canonicalization failures
    Given a repository with a project directory that cannot be canonicalized
    When the project directory is loaded
    Then exactly one project directory should be returned

  Scenario: Configuration path lookup fails without config
    Given a repository with a single project directory
    When the configuration path is requested
    Then configuration path lookup should fail with "project not initialized"

  Scenario: Configuration paths must exist
    Given a repository with a .kanbus.yml file referencing a missing path
    When project directories are discovered
    Then project discovery should fail with "kanbus path not found"

  Scenario: Project discovery fails with invalid configuration
    Given a repository with an invalid .kanbus.yml file
    When project directories are discovered
    Then project discovery should fail with "unknown configuration fields"

  Scenario: Configuration paths may include blank lines
    Given a repository with a .kanbus.yml file referencing a valid path with blank lines
    When project directories are discovered
    Then project discovery should include the referenced path

  Scenario: Dotfile paths are ignored
    Given a repository with a .kanbus file referencing another project
    When project directories are discovered
    Then project discovery should return no projects

  Scenario: Dotfile paths are ignored when missing
    Given a repository with a .kanbus file referencing a missing path
    When project directories are discovered
    Then project discovery should return no projects

  Scenario: Project discovery without git finds no dotfile paths
    Given a non-git directory without projects
    When project directories are discovered
    Then project discovery should return no projects

  Scenario: Project discovery fails when root is unreadable
    Given a repository directory that is unreadable
    When project directories are discovered
    Then project discovery should fail with "Permission denied"

  Scenario: Git root must point to a directory
    Given a repository with a fake git root pointing to a file
    When project directories are discovered
    Then project discovery should return no projects

  Scenario: Configuration search stops at filesystem root
    When kanbus configuration paths are discovered from the filesystem root
    Then project discovery should return no projects
