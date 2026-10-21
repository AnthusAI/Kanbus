Feature: Missing project_id is reported only where realtime matters
  A repository without project_id in .kanbus.yml cannot use realtime updates.
  Ordinary commands stay silent about it even when a broker is configured for
  every repository by the user environment. Doctor explains it as a warning.

  Scenario: An ordinary command stays silent when project_id is absent and a broker is configured
    Given a Kanbus project with default configuration
    And the Kanbus configuration has no project_id
    And the environment variable "KANBUS_REALTIME_BROKER" is set to "mqtt://127.0.0.1:1"
    When I run "kanbus create Quiet realtime"
    Then the command should succeed
    And stderr should not contain "Realtime updates are off"
    And stderr should not contain "project_id"

  Scenario: Doctor warns with an explanation when project_id is absent and a broker is configured
    Given a Kanbus project with default configuration
    And the Kanbus configuration has no project_id
    And the environment variable "KANBUS_REALTIME_BROKER" is set to "mqtt://127.0.0.1:1"
    When I run "kanbus doctor"
    Then the command should succeed
    And stdout should contain "warning: Realtime updates are off for this project because .kanbus.yml has no project_id."
    And stdout should contain "Run 'kbs migrate project-id' once on the repository's integration branch and commit .kanbus.yml"
    And stdout should contain "Every machine using this repository needs kbs 0.40.0 or later first."

  Scenario: Doctor does not mention realtime when the broker is off
    Given a Kanbus project with default configuration
    And the Kanbus configuration has no project_id
    And the environment variable "KANBUS_REALTIME_BROKER" is set to "off"
    When I run "kanbus doctor"
    Then the command should succeed
    And stdout should not contain "Realtime updates are off"
