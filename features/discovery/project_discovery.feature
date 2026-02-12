@wip
Feature: Project discovery
  As a Taskulus user
  I want Taskulus to discover projects by convention
  So that shared and local issues are scoped to my working directory

  Scenario: Downward discovery finds nested projects
    Given a repository with nested project directories
    When I run "tsk list"
    Then issues from all discovered projects should be listed

  Scenario: Downward discovery does not walk above cwd
    Given a repository with a project directory above the current directory
    When I run "tsk list"
    Then no issues should be listed

  Scenario: Local projects are discovered alongside shared projects
    Given a project directory with a sibling project-local directory
    When I run "tsk list"
    Then local issues should be included

  Scenario: Local issues can be excluded
    Given a project directory with a sibling project-local directory
    When I run "tsk list --no-local"
    Then local issues should not be listed

  Scenario: Local-only filtering
    Given a project directory with a sibling project-local directory
    When I run "tsk list --local-only"
    Then only local issues should be listed

  Scenario: Local-only conflicts with no-local
    Given a project directory with a sibling project-local directory
    When I run "tsk list --local-only --no-local"
    Then the command should fail with exit code 1
    And stderr should contain "local-only conflicts with no-local"

  Scenario: Dotfile adds external projects
    Given a repository with a .taskulus file referencing another project
    When I run "tsk list"
    Then issues from the referenced project should be listed
