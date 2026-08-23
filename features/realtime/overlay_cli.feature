Feature: Overlay CLI commands
  Scenario: Run overlay GC on default project
    Given a Kanbus project with default configuration
    And an overlay snapshot "kanbus-test01" updated at "2099-01-01T23:00:00Z"
    When I run "kanbus overlay gc"
    Then the command should succeed
    And stdout should contain "overlay gc complete (1 project(s))"

  Scenario: Run overlay GC on all projects
    Given a Kanbus project with default configuration
    When I run "kanbus overlay gc --all"
    Then the command should succeed
    And stdout should contain "overlay gc complete (1 project(s))"

  Scenario: Run overlay GC on unknown project
    Given a Kanbus project with default configuration
    When I run "kanbus overlay gc --project unknown"
    Then the command should fail with exit code 1
    And stderr should contain "unknown project label"

  Scenario: Reconcile overlay
    Given a Kanbus project with default configuration
    When I run "kanbus overlay reconcile"
    Then the command should succeed
    And stdout should contain "overlay reconcile complete"

  Scenario: Reconcile overlay on unknown project
    Given a Kanbus project with default configuration
    When I run "kanbus overlay reconcile --project unknown"
    Then the command should fail with exit code 1
    And stderr should contain "unknown project label"

  Scenario: Install overlay git hooks
    Given a Kanbus project with default configuration
    When I run "kanbus overlay install-hooks"
    Then the command should succeed
    And stdout should contain "overlay hooks installed"
