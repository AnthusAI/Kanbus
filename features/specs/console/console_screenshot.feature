@wip
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

  Scenario: Screenshot command writes a PNG to a custom output path
    Given the console server is running
    And screenshot capture is mocked to succeed
    When I run "kanbus console screenshot --output exports/board.png"
    Then the command should succeed
    And stdout should contain "exports/board.png"
    And a PNG file should exist at "exports/board.png"

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

  @console @console-server @slow
  Scenario: Screenshot command captures the live board UI
    Given an issue "kanbus-shot" exists with title "Screenshot visible issue"
    And the console server is running
    When I run "kanbus console screenshot --output kanbus-board-live.png"
    Then the command should succeed
    And a PNG file should exist at "kanbus-board-live.png"
    And the PNG file at "kanbus-board-live.png" should be larger than 10000 bytes
