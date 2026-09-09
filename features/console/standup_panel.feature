@console
Feature: Console standup in the Now panel
  As a Kanbus console user
  I want to generate standup reports from the Current Status panel
  So that I can prepare for meetings without using the CLI

  Background:
    Given the console is open

  Scenario: Now panel shows Standup button
    When I switch to the "Now" view
    Then the now standup button should be visible

  Scenario: Generate meeting-script succeeds and shows report sections
    Given no issues exist in the console
    And a status issue "Alpha task" updated at "2026-01-01T10:00:00.000Z"
    And the status issue "Alpha task" has right-now summary "Working on alpha"
    When I switch to the "Now" view
    And I open the standup drawer
    And I select the standup profile "meeting-script"
    And I generate the standup report
    Then the standup drawer should show section "Yesterday"
    And the standup drawer should show section "Today"
    And the standup drawer should show section "Blockers"
    And the standup drawer should show section "Likely questions"
    And the standup drawer result should mention "Working on alpha"

  Scenario: Switch to director-brief and generate succeeds
    Given no issues exist in the console
    And a status issue "Beta task" updated at "2026-01-02T10:00:00.000Z"
    And the status issue "Beta task" has right-now summary "Board health work"
    When I switch to the "Now" view
    And I open the standup drawer
    And I select the standup profile "director-brief"
    And I generate the standup report
    Then the standup drawer should show section "Health"
    And the standup drawer should show section "Momentum"
    And the standup drawer should show section "Risks"
    And the standup drawer should show section "Blockers"
    And the standup drawer result should mention "Board health work"

  Scenario: Generation failure surfaces error
    Given no issues exist in the console
    And a status issue "Gamma task" updated at "2026-01-03T10:00:00.000Z"
    And standup generation is configured to fail
    When I switch to the "Now" view
    And I open the standup drawer
    And I generate the standup report
    Then the standup drawer should show error "standup generation failed"
    And the standup drawer should not show a success result

  Scenario: Copy places report text on clipboard
    Given no issues exist in the console
    And a status issue "Delta task" updated at "2026-01-04T10:00:00.000Z"
    And the status issue "Delta task" has right-now summary "Copy test work"
    When I switch to the "Now" view
    And I open the standup drawer
    And I generate the standup report
    And I copy the standup report
    Then the standup clipboard should contain "Copy test work"

  @console-server
  Scenario: Console server standup API generates meeting-script for the board
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"
    And an issue "kanbus-std-console" exists with status "in_progress"
    And issue "kanbus-std-console" has right now summary "Console API standup work."
    And the console server is running
    When I request a standup report from the console API with profile "meeting-script"
    Then the standup API response should have profile "meeting-script"
    And the standup API response should include section "Today"
    And the standup API response text should mention "Console API standup work."
