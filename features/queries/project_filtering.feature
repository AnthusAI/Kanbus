Feature: Project filtering
  As a Kanbus user with virtual projects
  I want to filter issues by project
  So that I can focus on work from a specific project

  Scenario: Filter issues by project name
    Given a Kanbus project with virtual projects configured
    And issues exist in multiple virtual projects
    When I run "kanbus list --project alpha"
    Then stdout should contain issues from "alpha"
    And stdout should not contain issues from other projects

  Scenario: Filter by current project name
    Given a Kanbus project with virtual projects configured
    And issues exist in multiple virtual projects
    When I run "kanbus list --project kbs"
    Then stdout should contain issues from the current project only

  Scenario: Filter by multiple projects
    Given a Kanbus project with virtual projects configured
    And issues exist in multiple virtual projects
    When I run "kanbus list --project alpha --project beta"
    Then stdout should contain issues from "alpha"
    And stdout should contain issues from "beta"
    And stdout should not contain issues from the current project

  Scenario: Project filter combined with local-only
    Given a Kanbus project with virtual projects configured
    And a virtual project "alpha" has local issues
    When I run "kanbus list --project alpha --local-only"
    Then stdout should contain only local issues from "alpha"

  Scenario: Project filter combined with no-local
    Given a Kanbus project with virtual projects configured
    And a virtual project "alpha" has shared and local issues
    When I run "kanbus list --project alpha --no-local"
    Then stdout should contain only shared issues from "alpha"

  Scenario: Unknown project name is rejected
    Given a Kanbus project with virtual projects configured
    When I run "kanbus list --project nonexistent"
    Then the command should fail with exit code 1
    And stderr should contain "unknown project"

  Scenario: Project filter works with other filters
    Given a Kanbus project with virtual projects configured
    And issues exist in multiple virtual projects with various statuses
    When I run "kanbus list --project alpha --status open"
    Then stdout should contain only open issues from "alpha"

  Scenario: No project filter shows all projects
    Given a Kanbus project with virtual projects configured
    And issues exist in multiple virtual projects
    When I run "kanbus list"
    Then stdout should contain issues from all projects
