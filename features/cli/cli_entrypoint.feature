Feature: CLI entrypoint
  As a Kanbus user
  I want the CLI entrypoint to provide help output
  So that I can discover available commands

  Scenario: CLI entrypoint shows help
    When I run the CLI entrypoint with --help
    Then the command should succeed
    And stdout should contain "Usage:"

  Scenario: CLI entrypoint reports failures
    Given an empty git repository
    When I run the CLI entrypoint with "list"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"
