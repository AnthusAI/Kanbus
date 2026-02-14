Feature: Example project setup with Kanbus
  As a Kanbus user
  I want a sample project that uses Kanbus setup utilities
  So that integration behavior is validated end-to-end

  Scenario: Create Rube Goldberg example project
    Given the "Rube Goldberg" example project does not exist
    When I create the "Rube Goldberg" example project
    And I run "kanbus init" in the "Rube Goldberg" example project
    And I add a README stub to the "Rube Goldberg" example project
    And I run "kanbus setup agents" in the "Rube Goldberg" example project
    Then the "Rube Goldberg" example project should contain a README stub
    And the "Rube Goldberg" example project should contain .kanbus.yml
    And the "Rube Goldberg" example project should contain the project directory
    And the "Rube Goldberg" example project should contain AGENTS.md with Kanbus instructions
    And the "Rube Goldberg" example project should contain CONTRIBUTING_AGENT.md
