@console
Feature: Console project filter
  As a Kanbus user with virtual projects
  I want the console to show a project filter when multiple projects exist
  So that I can focus the board on specific projects

  Scenario: Project filter appears when virtual projects are configured
    Given the console is open with virtual projects configured
    Then the project filter should be visible in the navigation bar

  Scenario: Project filter is hidden for single project
    Given the console is open
    And no virtual projects are configured
    Then the project filter should not be visible

  Scenario: Project filter lists all projects
    Given the console is open with virtual projects "alpha" and "beta" configured
    Then the project filter should list "kbs"
    And the project filter should list "alpha"
    And the project filter should list "beta"

  Scenario: Selecting a project filters the board
    Given the console is open with virtual projects configured
    And issues exist in multiple projects
    When I select project "alpha" in the project filter
    Then I should only see issues from "alpha"

  Scenario: Selecting all projects shows everything
    Given the console is open with virtual projects configured
    And issues exist in multiple projects
    When I select all projects in the project filter
    Then I should see issues from all projects

  Scenario: Local filter appears when local issues exist
    Given the console is open
    And local issues exist in the current project
    Then the local issues filter should be visible in the navigation bar

  Scenario: Local filter is hidden when no local issues exist
    Given the console is open
    And no local issues exist in any project
    Then the local issues filter should not be visible

  Scenario: Local filter combined with project filter
    Given the console is open with virtual projects configured
    And local issues exist in virtual project "alpha"
    When I select project "alpha" in the project filter
    And I select "local only" in the local filter
    Then I should only see local issues from "alpha"

  Scenario: Project filter combined with shared-only
    Given the console is open with virtual projects configured
    When I select project "alpha" in the project filter
    And I select "project only" in the local filter
    Then I should only see shared issues from "alpha"

  Scenario: Project filter persists across reloads
    Given the console is open with virtual projects configured
    When I select project "alpha" in the project filter
    And the console is reloaded
    Then project "alpha" should still be selected in the project filter
