@cli
Feature: Console board screenshot
  As a Kanbus user or agent
  I want a CLI command that saves a PNG of the board UI
  So that I can share or archive what the board looks like without manual browser capture

  Background:
    Given a Kanbus project with default configuration

  Scenario: Screenshot command writes a PNG with the default output path
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot"
    Then the command should succeed
    And stdout should contain "kanbus-board.png"
    And a PNG file should exist at "kanbus-board.png"
    And screenshot capture prerequisites should be verified

  Scenario: Screenshot command writes a PNG to a custom output path
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --output exports/board.png"
    Then the command should succeed
    And stdout should contain "exports/board.png"
    And a PNG file should exist at "exports/board.png"

  Scenario: Screenshot command defaults to light appearance mode
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot"
    Then the command should succeed
    And the screenshot appearance mode should be "light"

  Scenario: Screenshot command accepts dark appearance mode
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --mode dark"
    Then the command should succeed
    And the screenshot appearance mode should be "dark"

  Scenario: Screenshot command rejects invalid appearance mode
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --mode sepia"
    Then the command should fail with exit code 1
    And stderr should contain "appearance mode must be light or dark"

  Scenario: Screenshot command accepts all issue types view
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --view all"
    Then the command should succeed
    And the screenshot capture view should be "all"

  Scenario: Screenshot command accepts epics view
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --view epics"
    Then the command should succeed
    And the screenshot capture view should be "epics"

  Scenario: Screenshot command accepts initiatives view
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --view initiatives"
    Then the command should succeed
    And the screenshot capture view should be "initiatives"

  Scenario: Screenshot command accepts issues view
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --view issues"
    Then the command should succeed
    And the screenshot capture view should be "issues"

  Scenario: Screenshot command expands all columns when requested
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --expand-all"
    Then the command should succeed
    And screenshot capture expand-all should be enabled

  Scenario: Screenshot command expands a specific column when requested
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --expand backlog"
    Then the command should succeed
    And the screenshot capture expanded columns should include "backlog"

  Scenario: Screenshot command collapses a specific column when requested
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --collapse in_progress"
    Then the command should succeed
    And the screenshot capture collapsed columns should include "in_progress"

  Scenario: Screenshot command supports multiple expand and collapse flags
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --expand backlog --expand closed --collapse in_progress"
    Then the command should succeed
    And the screenshot capture expanded columns should include "backlog"
    And the screenshot capture expanded columns should include "closed"
    And the screenshot capture collapsed columns should include "in_progress"

  Scenario: Screenshot command supports newsroom board layout flags
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --view all --expand-all"
    Then the command should succeed
    And the screenshot capture view should be "all"
    And screenshot capture expand-all should be enabled

  Scenario: Screenshot command rejects invalid view
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --view pods"
    Then the command should fail with exit code 1
    And stderr should contain "view must be one of"

  Scenario: Screenshot command fails with a clear error when headless browser is unavailable
    Given the console server is running
    And screenshot capture is mocked as unavailable
    When I run "kanbus console screenshot"
    Then the command should fail with exit code 1
    And stderr should contain "headless browser"
    And stderr should contain "playwright"

  Scenario: Screenshot command fails when the console server is not running
    Given the console server is not running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot"
    Then the command should fail with exit code 1
    And stderr should contain "Console server is not running"

  Scenario: Screenshot command honors CONSOLE_PORT when resolving the server
    Given the console server is running
    And the environment variable CONSOLE_PORT is set to the console server port
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot"
    Then the command should succeed
    And a PNG file should exist at "kanbus-board.png"

  Scenario: Screenshot command ignores invalid CONSOLE_PORT and uses project configuration
    Given the environment variable "CONSOLE_PORT" is set to "not-a-port"
    And the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot"
    Then the command should succeed
    And a PNG file should exist at "kanbus-board.png"

  Scenario: Screenshot command uses the default console port when configuration is missing
    Given a Kanbus repository without a .kanbus.yml file
    And the environment variable "CONSOLE_PORT" is not set
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot"
    Then the command should fail with exit code 1
    And stderr should contain "Console server is not running"

  Scenario: Screenshot command fails when the capture script cannot be located
    Given the console server is running
    And the capture script cannot be located
    When I run "kanbus console screenshot"
    Then the command should fail with exit code 1
    And stderr should contain "capture script not found"

  Scenario: Screenshot command fails when Node.js is not available for capture
    Given the console server is running
    And Node.js is unavailable for screenshot capture
    When I run "kanbus console screenshot"
    Then the command should fail with exit code 1
    And stderr should contain "Node.js"

  @console @console-server @slow
  Scenario: Screenshot command captures the live board UI
    Given an issue "kanbus-shot" exists with title "Screenshot visible issue"
    And the console server is running
    When I run "kanbus console screenshot --output kanbus-board-live.png"
    Then the command should succeed
    And a PNG file should exist at "kanbus-board-live.png"
    And the PNG file at "kanbus-board-live.png" should be larger than 10000 bytes
