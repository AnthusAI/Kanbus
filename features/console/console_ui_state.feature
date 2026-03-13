@cli
Feature: Console UI state commands
  As a Kanbus user or agent
  I want CLI commands to read and write the console UI state
  So that I can inspect and control the console from scripts and workflows

  Scenario: Create focus flag is deprecated
    Given a Kanbus project with default configuration
    When I run "kanbus create \"Deprecated focus\" --focus"
    Then the command should fail
    And stderr should contain "deprecated"
    And stderr should contain "pub/sub convention"

  # ---------------------------------------------------------------------------
  # kbs console focus
  # ---------------------------------------------------------------------------

  Scenario: Focus command is deprecated
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    When I run "kanbus console focus kanbus-abc"
    Then the command should fail
    And stderr should contain "deprecated"
    And stderr should contain "pub/sub convention"

  Scenario: Focus command with comment flag is deprecated
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    When I run "kanbus console focus kanbus-abc --comment abc123"
    Then the command should fail
    And stderr should contain "deprecated"

  Scenario: Focus command still fails fast as deprecated even when issue does not exist
    Given a Kanbus project with default configuration
    When I run "kanbus console focus kanbus-does-not-exist"
    Then the command should fail
    And stderr should contain "deprecated"

  # ---------------------------------------------------------------------------
  # kbs console unfocus
  # ---------------------------------------------------------------------------

  Scenario: Unfocus command is deprecated
    Given a Kanbus project with default configuration
    When I run "kanbus console unfocus"
    Then the command should fail
    And stderr should contain "deprecated"

  # ---------------------------------------------------------------------------
  # kbs console view
  # ---------------------------------------------------------------------------

  Scenario: View command with "issues" mode is deprecated
    Given a Kanbus project with default configuration
    When I run "kanbus console view issues"
    Then the command should fail
    And stderr should contain "deprecated"

  Scenario: View command with "epics" mode is deprecated
    Given a Kanbus project with default configuration
    When I run "kanbus console view epics"
    Then the command should fail
    And stderr should contain "deprecated"

  Scenario: View command with "initiatives" mode is deprecated
    Given a Kanbus project with default configuration
    When I run "kanbus console view initiatives"
    Then the command should fail
    And stderr should contain "deprecated"

  # ---------------------------------------------------------------------------
  # kbs console search
  # ---------------------------------------------------------------------------

  Scenario: Search command is deprecated
    Given a Kanbus project with default configuration
    When I run "kanbus console search auth"
    Then the command should fail
    And stderr should contain "deprecated"

  # ---------------------------------------------------------------------------
  # kbs console status (server offline)
  # ---------------------------------------------------------------------------

  @skip
  Scenario: Status command reports server offline when console server is not running
    Given a Kanbus project with default configuration
    And the console server is not running
    When I run "kanbus console status"
    Then the command should succeed
    And stdout should contain "Console server is not running"

  # ---------------------------------------------------------------------------
  # kbs console get (server offline)
  # ---------------------------------------------------------------------------

  @skip
  Scenario: Get focus reports server offline when console server is not running
    Given a Kanbus project with default configuration
    And the console server is not running
    When I run "kanbus console get focus"
    Then the command should succeed
    And stdout should contain "Console server is not running"

  @skip
  Scenario: Get view reports server offline when console server is not running
    Given a Kanbus project with default configuration
    And the console server is not running
    When I run "kanbus console get view"
    Then the command should succeed
    And stdout should contain "Console server is not running"

  @skip
  Scenario: Get search reports server offline when console server is not running
    Given a Kanbus project with default configuration
    And the console server is not running
    When I run "kanbus console get search"
    Then the command should succeed
    And stdout should contain "Console server is not running"

  Scenario: Get with an unknown field fails
    Given a Kanbus project with default configuration
    And the console server is not running
    When I run "kanbus console get unknown-field"
    Then the command should fail

  # ---------------------------------------------------------------------------
  # kbs console status and get (server online) — requires running console server
  # ---------------------------------------------------------------------------

  @console @console-server
  Scenario: Status shows all state fields when console server is running
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    And the console server is running
    And the console focused issue is "kanbus-abc"
    And the console view mode is "issues"
    And the console search query is "login"
    When I run "kanbus console status"
    Then the command should succeed
    And stdout should contain "kanbus-abc"
    And stdout should contain "issues"
    And stdout should contain "login"

  @console @console-server
  Scenario: Get focus prints focused issue ID
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    And the console server is running
    And the console focused issue is "kanbus-abc"
    When I run "kanbus console get focus"
    Then the command should succeed
    And stdout should contain "kanbus-abc"

  @console @console-server
  Scenario: Get focus prints "none" when no issue is focused
    Given a Kanbus project with default configuration
    And the console server is running
    And no issue is focused in the console
    When I run "kanbus console get focus"
    Then the command should succeed
    And stdout should contain "none"

  @console @console-server
  Scenario: Get view prints current view mode
    Given a Kanbus project with default configuration
    And the console server is running
    And the console view mode is "epics"
    When I run "kanbus console get view"
    Then the command should succeed
    And stdout should contain "epics"

  @console @console-server
  Scenario: Get search prints active search query
    Given a Kanbus project with default configuration
    And the console server is running
    And the console search query is "auth bug"
    When I run "kanbus console get search"
    Then the command should succeed
    And stdout should contain "auth bug"

  @console @console-server
  Scenario: Focus command is deprecated while server is running
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    And the console server is running
    When I run "kanbus console focus kanbus-abc"
    Then the command should fail
    And stderr should contain "deprecated"

  @console @console-server
  Scenario: Unfocus command is deprecated while server is running
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    And the console server is running
    And the console focused issue is "kanbus-abc"
    When I run "kanbus console unfocus"
    Then the command should fail
    And stderr should contain "deprecated"

  @console @console-server
  Scenario: UI state persists across server restarts
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    And the console server is running
    And the console focused issue is "kanbus-abc"
    When the console server is restarted
    And I run "kanbus console get focus"
    Then the command should succeed
    And stdout should contain "kanbus-abc"
