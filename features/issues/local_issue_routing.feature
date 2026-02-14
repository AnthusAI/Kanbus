Feature: Local issue routing

  Scenario: Create a local issue
    Given a Kanbus project with default configuration
    When I run "kanbus create --local Local task"
    Then the command should succeed
    And a local issue file should be created in the local issues directory
    And .gitignore should include "project-local/"

  Scenario: Promote a local issue to shared
    Given a Kanbus project with default configuration
    And a local issue "kanbus-local01" exists
    When I run "kanbus promote kanbus-local01"
    Then the command should succeed
    And issue "kanbus-local01" should exist in the shared issues directory
    And issue "kanbus-local01" should not exist in the local issues directory

  Scenario: Localize a shared issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-shared01" exists
    When I run "kanbus localize kanbus-shared01"
    Then the command should succeed
    And issue "kanbus-shared01" should exist in the local issues directory
    And issue "kanbus-shared01" should not exist in the shared issues directory
    And .gitignore should include "project-local/"

  Scenario: Promote fails when project-local is missing
    Given a Kanbus project with default configuration
    When I run "kanbus promote kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "project-local not initialized"

  Scenario: Promote fails when local issue is missing
    Given a Kanbus project with default configuration
    And a local issue "kanbus-other" exists
    When I run "kanbus promote kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Promote fails when shared issue already exists
    Given a Kanbus project with default configuration
    And a local issue "kanbus-dupe01" exists
    And an issue "kanbus-dupe01" exists
    When I run "kanbus promote kanbus-dupe01"
    Then the command should fail with exit code 1
    And stderr should contain "already exists"

  Scenario: Localize fails when local issue already exists
    Given a Kanbus project with default configuration
    And a local issue "kanbus-dupe02" exists
    And an issue "kanbus-dupe02" exists
    When I run "kanbus localize kanbus-dupe02"
    Then the command should fail with exit code 1
    And stderr should contain "already exists"

  Scenario: Localize fails when shared issue is missing
    Given a Kanbus project with default configuration
    When I run "kanbus localize kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Promote fails without a project
    Given an empty git repository
    When I run "kanbus promote kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Localize fails without a project
    Given an empty git repository
    When I run "kanbus localize kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Local creation preserves existing gitignore entry
    Given a Kanbus project with default configuration
    And .gitignore already includes "project-local/"
    When I run "kanbus create --local Local task"
    Then the command should succeed
    And .gitignore should include "project-local/" only once

  Scenario: Local creation appends gitignore with newline
    Given a Kanbus project with default configuration
    And a .gitignore without a trailing newline exists
    When I run "kanbus create --local Local task"
    Then the command should succeed
    And .gitignore should include "project-local/"

  Scenario: Local create fails when title already exists in local issues
    Given a Kanbus project with default configuration
    And a local issue "kanbus-local01" exists
    When I run "kanbus create --local local"
    Then the command should fail with exit code 1
    And stderr should contain "duplicate title"
    And stderr should contain "kanbus-local01"
    And the local issues directory should contain 1 issue file
