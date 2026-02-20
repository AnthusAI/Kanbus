Feature: Pytest migration coverage
  As a Kanbus maintainer
  I want pytest coverage moved into Behave scenarios
  So the Python test suite is consistent

  Scenario: Load minimal configuration and defaults
    Given a Kanbus project with a minimal configuration file
    When the configuration is loaded
    Then the project key should be "tsk"
    And the project directory should be "project"
    And the hierarchy should include "initiative"

  Scenario: Missing configuration file reports error
    Given a Kanbus repository without a .kanbus.yml file
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "configuration file not found"

  Scenario: Kanbusr shim exposes version and exports
    When I import the kanbusr shim
    Then the kanbusr version should match kanbus
    And the kanbusr shim should expose "__all__"

  Scenario: Issue data validates dependencies and comments
    When I build a sample issue with dependency "tsk-0" and comment author "me"
    Then the issue identifier should be "tsk-1"
    And the dependency type should be "blocked-by"
    And the comment author should be "me"

  Scenario: Dependency link requires a type
    When I build a dependency link with empty type
    Then the dependency link should fail validation
