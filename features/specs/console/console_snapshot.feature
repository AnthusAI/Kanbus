Feature: Console snapshot
  As a Taskulus user
  I want a console snapshot command
  So that the console server can stream updates

  Scenario: Snapshot emits config and issues
    Given a Taskulus project with default configuration
    And a Taskulus project with a console configuration file
    When I run "tsk create Snapshot issue"
    Then the command should succeed
    When I run "tsk console snapshot"
    Then the command should succeed
    And stdout should contain "\"config\""
    And stdout should contain "\"issues\""
