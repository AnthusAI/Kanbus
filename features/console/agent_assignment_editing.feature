@console @kbs-daf353
Feature: Console routing assignment editing
  As a Kanbus user
  I want to choose, change or clear an issue's routing assignment
  So that I control which agent will work on it without hand-editing labels

  Assignment is project-level: the choices are the router classes and provider
  profiles in the project's own configuration. The write is refused while the
  router is running the issue, and, like the other console writes, only from
  localhost (covered by Rust-level tests, see issue_write_controls.feature).

  Background:
    Given the console is open
    And the console has only these issues:
      | id            | title          | status |
      | kbs-assign    | Assign me      | open   |
      | kbs-running   | Running issue  | in_progress |
    And the Kanbus configuration has a router with class "implementation" using provider "codex-default"
    And the issue "kbs-assign" has labels "bug,ui"
    And the issue "kbs-running" has labels "agent-class:implementation"

  Scenario: Choosing a class keeps the other labels and resolves the assignment
    When I set the routing assignment through the issue write API for "kbs-assign" to class "implementation"
    Then the issue write API response should be successful with labels "agent-class:implementation,bug,ui"
    And the issue write API response should show agent assignment "class" "implementation"

  Scenario: Choosing a provider replaces the class and never leaves two routes
    When I set the routing assignment through the issue write API for "kbs-assign" to class "implementation"
    And I set the routing assignment through the issue write API for "kbs-assign" to provider "codex-default"
    Then the issue write API response should be successful with labels "agent-provider:codex-default,bug,ui"
    And the issue write API response should show agent assignment "provider" "codex-default"

  Scenario: Clearing removes only the routing label
    When I set the routing assignment through the issue write API for "kbs-assign" to class "implementation"
    And I clear the routing assignment through the issue write API for "kbs-assign"
    Then the issue write API response should be successful with labels "bug,ui"
    And the issue write API response should show no agent assignment

  Scenario: An unknown class or provider is rejected
    When I set the routing assignment through the issue write API for "kbs-assign" to class "missing"
    Then the issue write API response should fail with status 400 and error containing "unknown agent class"
    When I set the routing assignment through the issue write API for "kbs-assign" to provider "missing"
    Then the issue write API response should fail with status 400 and error containing "unknown provider profile"

  Scenario: An issue the router is running cannot be reassigned
    When I clear the routing assignment through the issue write API for "kbs-running"
    Then the issue write API response should fail with status 400 and error containing "router is running"
