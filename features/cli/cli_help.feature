Feature: CLI help
  As a Taskulus user
  I want CLI help output
  So that I can discover available commands

  Scenario: CLI help shows usage
    Given a Taskulus project with default configuration
    When I run "tsk --help"
    Then the command should succeed
    And stdout should contain "Usage"

  Scenario: CLI rejects unknown options
    Given a Taskulus project with default configuration
    When I run "tsk --unknown"
    Then the command should fail
    And stderr should contain "--unknown"
