@slow
Feature: Embedded console assets
  As a Kanbus user
  I want to download and run the console as a single binary
  So that I can access the console without configuration

  Scenario: Zero-config console execution
    Given I have the kanbus-console binary with embedded assets
    And CONSOLE_ASSETS_ROOT is not set
    When I start the console server
    Then the server starts successfully
    And the startup message shows "(embedded assets)"
    And I can access http://127.0.0.1:5174/
    And the UI index.html loads
    And JavaScript assets load from /assets/
    And CSS assets load from /assets/
    And API endpoint /api/config responds

  Scenario: Filesystem override takes precedence
    Given I have the kanbus-console binary with embedded assets
    And I set CONSOLE_ASSETS_ROOT to a custom directory
    And I place custom assets in that directory
    When I start the console server
    Then assets are served from the filesystem path
    And embedded assets are NOT used

  Scenario: Development build uses filesystem only
    Given I build console_local without --features embed-assets
    And I set CONSOLE_ASSETS_ROOT to apps/console/dist
    When I start the console server
    Then assets are served from apps/console/dist
    And the binary does not contain embedded assets
