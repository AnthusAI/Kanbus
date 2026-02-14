Feature: CLI help
  As a Kanbus user
  I want CLI help output
  So that I can discover available commands

  Scenario: CLI help shows usage
    Given a Kanbus project with default configuration
    When I run "kanbus --help"
    Then the command should succeed
    And stdout should contain "Usage"

  Scenario: CLI rejects unknown options
    Given a Kanbus project with default configuration
    When I run "kanbus --unknown"
    Then the command should fail
    And stderr should contain "--unknown"
