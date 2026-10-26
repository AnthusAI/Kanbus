Feature: Project context
  As a Kanbus user
  I want every issue command to read the project configuration once and report a broken configuration clearly
  So that a malformed .kanbus.yml is never silently worked around

  Scenario Outline: A malformed configuration fails the command with one configuration error
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Existing issue"
    And the Kanbus configuration file contains malformed YAML
    When I run "<command>"
    Then the command should fail with exit code 1
    And stderr should contain "configuration is not valid YAML"

    Examples:
      | command                                        |
      | kanbus list                                    |
      | kanbus show kanbus-aaa                         |
      | kanbus create Brand new issue                  |
      | kanbus update kanbus-aaa --status in_progress  |

  Scenario: A missing configuration keeps the project not initialized error
    Given an empty repository without a .kanbus.yml file
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: A missing configuration keeps the create error
    Given an empty repository without a .kanbus.yml file
    When I run "kanbus create Brand new issue"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"
