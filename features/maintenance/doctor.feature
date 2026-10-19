Feature: Doctor diagnostics
  As a Kanbus maintainer
  I want a doctor command that validates the environment
  So that setup issues are visible quickly

  Scenario: Doctor succeeds with a valid project
    Given a Kanbus project with default configuration
    When I run "kanbus doctor"
    Then the command should succeed
    And stdout should contain "ok"

  Scenario: Doctor fails without a project
    Given an empty git repository
    When I run "kanbus doctor"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Doctor fails without a git repository
    Given a directory that is not a git repository
    When I run "kanbus doctor"
    Then the command should fail with exit code 1
    And stderr should contain "not a git repository"

  Scenario: Doctor fails with invalid configuration
    Given a Kanbus project with an invalid configuration containing unknown fields
    When I run "kanbus doctor"
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  Scenario: Doctor fails when configuration path lookup fails
    Given a Kanbus project with default configuration
    And configuration path lookup will fail
    When I run doctor diagnostics directly
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

  Scenario: Doctor warns when events are enabled but gitignored
    Given a Kanbus project with default configuration
    And the repository .gitignore contains "project/events/"
    When I run "kanbus doctor"
    Then the command should succeed
    And stdout should contain "warning: events are enabled but project/events is gitignored"
    And stdout should contain "remove the rule"

  Scenario: Doctor does not warn about gitignored events when events are turned off
    Given a Kanbus project with default configuration
    And the Kanbus configuration disables events
    And the repository .gitignore contains "project/events/"
    When I run "kanbus doctor"
    Then the command should succeed
    And stdout should not contain "gitignored"
