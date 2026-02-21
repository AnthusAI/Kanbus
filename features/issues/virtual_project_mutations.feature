Feature: Issue mutations across virtual projects
  As a Kanbus user with virtual projects
  I want mutations to apply to the original issue in its original project
  So that no duplicates are created and source projects stay consistent

  Scenario: Update an issue from a virtual project
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-task01" exists in virtual project "alpha"
    When I run "kanbus update alpha-task01 --status in_progress"
    Then the command should succeed
    And the issue file in virtual project "alpha" should be updated
    And no issue file should be created in the current project

  Scenario: Close an issue from a virtual project
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-task01" exists in virtual project "alpha"
    When I run "kanbus close alpha-task01"
    Then the command should succeed
    And the issue file in virtual project "alpha" should have status "closed"

  Scenario: Comment on an issue from a virtual project
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-task01" exists in virtual project "alpha"
    And the current user is "dev@example.com"
    When I run "kanbus comment alpha-task01 "Cross-project comment""
    Then the command should succeed
    And issue "alpha-task01" in virtual project "alpha" should have 1 comment

  Scenario: Delete an issue from a virtual project
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-task01" exists in virtual project "alpha"
    When I run "kanbus delete alpha-task01"
    Then the command should succeed
    And the issue file should not exist in virtual project "alpha"

  Scenario: Show an issue from a virtual project
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-task01" exists in virtual project "alpha"
    When I run "kanbus show alpha-task01"
    Then the command should succeed
    And stdout should contain the source project label "alpha"

  Scenario: Promote a local issue within a virtual project
    Given a Kanbus project with virtual projects configured
    And a local issue "alpha-local01" exists in virtual project "alpha"
    When I run "kanbus promote alpha-local01"
    Then the command should succeed
    And issue "alpha-local01" should exist in virtual project "alpha" shared directory
    And issue "alpha-local01" should not exist in virtual project "alpha" local directory

  Scenario: Localize a shared issue within a virtual project
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-task01" exists in virtual project "alpha"
    When I run "kanbus localize alpha-task01"
    Then the command should succeed
    And issue "alpha-task01" should exist in virtual project "alpha" local directory
    And issue "alpha-task01" should not exist in virtual project "alpha" shared directory

  Scenario: Events are written to the source project event directory
    Given a Kanbus project with virtual projects configured
    And an issue "alpha-task01" exists in virtual project "alpha"
    When I run "kanbus update alpha-task01 --status in_progress"
    Then an event file should be created in virtual project "alpha" events directory
