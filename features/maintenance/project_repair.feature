Feature: Project repair
  As a Kanbus maintainer
  I want a repair command for missing project folders
  So that broken repositories can recover safely

  Scenario: Repair recreates missing directories
    Given a Kanbus project with default configuration
    And the issues directory is missing
    And the events directory is missing
    When I run "kanbus repair --yes"
    Then the issues directory should exist
    And the events directory should exist

  Scenario: Repair without --yes fails in non-interactive mode
    Given a Kanbus project with default configuration
    And the issues directory is missing
    When I run "kanbus repair"
    Then the command should fail with exit code 1
    And stderr should contain "re-run with --yes"

  Scenario: Repair no-ops when structure is healthy
    Given a Kanbus project with default configuration
    When I run "kanbus repair --yes"
    Then stdout should contain "Project structure is already healthy."
