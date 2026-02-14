Feature: Console snapshot
  As a Kanbus user
  I want a console snapshot command
  So that the console server can stream updates

  Scenario: Snapshot emits config and issues
    Given a Kanbus project with default configuration
    When I run "kanbus create Snapshot issue"
    Then the command should succeed
    When I run "kanbus console snapshot"
    Then the command should succeed
    And stdout should contain "\"config\""
    And stdout should contain "\"assignee\""
    And stdout should contain "\"time_zone\""
    And stdout should contain "\"status_colors\""
    And stdout should contain "\"type_colors\""
    And stdout should contain "\"priorities\""
    And stdout should contain "\"issues\""

  Scenario: Snapshot fails when configuration is missing
    Given a Kanbus project with default configuration
    And the Kanbus configuration file is missing
    When I run "kanbus console snapshot"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Snapshot fails when configuration is not a mapping
    Given a Kanbus project with default configuration
    And a Kanbus configuration file that is not a mapping
    When I run "kanbus console snapshot"
    Then the command should fail with exit code 1
    And stderr should contain "configuration must be a mapping"

  Scenario: Snapshot fails when issues directory is missing
    Given a Kanbus project with default configuration
    And the issues directory is missing
    When I run "kanbus console snapshot"
    Then the command should fail with exit code 1
    And stderr should contain "project/issues directory not found"

  Scenario: Snapshot fails when issues path is a file
    Given a Kanbus project with default configuration
    And the issues directory is a file
    When I run "kanbus console snapshot"
    Then the command should fail with exit code 1
    And stderr should contain "project/issues directory not found"

  Scenario: Snapshot fails when issues directory is unreadable
    Given a Kanbus project with default configuration
    And the issues directory is unreadable
    When I run "kanbus console snapshot"
    Then the command should fail with exit code 1
    And stderr should contain "Permission denied"

  Scenario: Snapshot fails when an issue file is invalid JSON
    Given a Kanbus project with default configuration
    And an issue file contains invalid JSON
    When I run "kanbus console snapshot"
    Then the command should fail with exit code 1
    And stderr should contain "issue file is invalid"

  Scenario: Snapshot fails when an issue file has invalid data
    Given a Kanbus project with default configuration
    And an issue file contains invalid issue data
    When I run "kanbus console snapshot"
    Then the command should fail with exit code 1
    And stderr should contain "issue file is invalid"

  Scenario: Snapshot fails when configuration path lookup fails
    Given a Kanbus project with default configuration
    And configuration path lookup will fail
    When I build a console snapshot directly
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

  Scenario: Snapshot ignores non-issue files
    Given a Kanbus project with default configuration
    And a non-issue file exists in the issues directory
    When I run "kanbus console snapshot"
    Then the command should succeed
    And stdout should contain "\"issues\""
