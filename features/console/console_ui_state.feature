@cli
Feature: Console UI state commands
  As a Kanbus user or agent
  I want CLI commands to read and write the console UI state
  So that I can inspect and control the console from scripts and workflows

  # ---------------------------------------------------------------------------
  # kbs console focus
  # ---------------------------------------------------------------------------

  Scenario: Focus command prints confirmation and exits successfully
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    When I run "kanbus console focus kanbus-abc"
    Then the command should succeed
    And stdout should contain "kanbus-abc"

  Scenario: Focus command with comment flag prints confirmation including comment
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    When I run "kanbus console focus kanbus-abc --comment abc123"
    Then the command should succeed
    And stdout should contain "kanbus-abc"
    And stdout should contain "abc123"

  Scenario: Focus command fails when the issue does not exist
    Given a Kanbus project with default configuration
    When I run "kanbus console focus kanbus-does-not-exist"
    Then the command should fail

  # ---------------------------------------------------------------------------
  # kbs console unfocus
  # ---------------------------------------------------------------------------

  Scenario: Unfocus command prints confirmation and exits successfully
    Given a Kanbus project with default configuration
    When I run "kanbus console unfocus"
    Then the command should succeed
    And stdout should contain "focus"

  # ---------------------------------------------------------------------------
  # kbs console view
  # ---------------------------------------------------------------------------

  Scenario: View command with "issues" mode prints confirmation and exits successfully
    Given a Kanbus project with default configuration
    When I run "kanbus console view issues"
    Then the command should succeed
    And stdout should contain "issues"

  Scenario: View command with "epics" mode prints confirmation and exits successfully
    Given a Kanbus project with default configuration
    When I run "kanbus console view epics"
    Then the command should succeed
    And stdout should contain "epics"

  Scenario: View command with "initiatives" mode prints confirmation and exits successfully
    Given a Kanbus project with default configuration
    When I run "kanbus console view initiatives"
    Then the command should succeed
    And stdout should contain "initiatives"

  # ---------------------------------------------------------------------------
  # kbs console search
  # ---------------------------------------------------------------------------

  Scenario: Search command prints confirmation and exits successfully
    Given a Kanbus project with default configuration
    When I run "kanbus console search auth"
    Then the command should succeed
    And stdout should contain "auth"

  # ---------------------------------------------------------------------------
  # kbs console status (server offline)
  # ---------------------------------------------------------------------------

  Scenario: Status command reports server offline when console server is not running
    Given a Kanbus project with default configuration
    And the console server is not running
    When I run "kanbus console status"
    Then the command should succeed
    And stdout should contain "Console server is not running"

  # ---------------------------------------------------------------------------
  # kbs console get (server offline)
  # ---------------------------------------------------------------------------

  Scenario: Get focus reports server offline when console server is not running
    Given a Kanbus project with default configuration
    And the console server is not running
    When I run "kanbus console get focus"
    Then the command should succeed
    And stdout should contain "Console server is not running"

  Scenario: Get view reports server offline when console server is not running
    Given a Kanbus project with default configuration
    And the console server is not running
    When I run "kanbus console get view"
    Then the command should succeed
    And stdout should contain "Console server is not running"

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

  @console
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

  @console
  Scenario: Get focus prints focused issue ID
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    And the console server is running
    And the console focused issue is "kanbus-abc"
    When I run "kanbus console get focus"
    Then the command should succeed
    And stdout should contain "kanbus-abc"

  @console
  Scenario: Get focus prints "none" when no issue is focused
    Given a Kanbus project with default configuration
    And the console server is running
    And no issue is focused in the console
    When I run "kanbus console get focus"
    Then the command should succeed
    And stdout should contain "none"

  @console
  Scenario: Get view prints current view mode
    Given a Kanbus project with default configuration
    And the console server is running
    And the console view mode is "epics"
    When I run "kanbus console get view"
    Then the command should succeed
    And stdout should contain "epics"

  @console
  Scenario: Get search prints active search query
    Given a Kanbus project with default configuration
    And the console server is running
    And the console search query is "auth bug"
    When I run "kanbus console get search"
    Then the command should succeed
    And stdout should contain "auth bug"

  @console
  Scenario: Focus command updates server state
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    And the console server is running
    When I run "kanbus console focus kanbus-abc"
    Then the command should succeed
    When I run "kanbus console get focus"
    Then stdout should contain "kanbus-abc"

  @console
  Scenario: Unfocus clears server focus state
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    And the console server is running
    And the console focused issue is "kanbus-abc"
    When I run "kanbus console unfocus"
    Then the command should succeed
    When I run "kanbus console get focus"
    Then stdout should contain "none"

  @console
  Scenario: UI state persists across server restarts
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Auth bug"
    And the console server is running
    And the console focused issue is "kanbus-abc"
    When the console server is restarted
    And I run "kanbus console get focus"
    Then the command should succeed
    And stdout should contain "kanbus-abc"
