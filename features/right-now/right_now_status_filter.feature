Feature: Now status filter
  As a Kanbus user
  I want Now to show in-progress work by default
  So that the feed is current work instead of the whole board

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Now lists only in-progress issues by default
    Given an issue "kanbus-rn-active" exists with status "in_progress"
    And an issue "kanbus-rn-ready" exists with status "open"
    When I run "kanbus now --list"
    Then the command should succeed
    And stdout should contain "kanbus-rn-active"
    And stdout should not contain "kanbus-rn-ready"

  Scenario: Now --status all lists every status
    Given an issue "kanbus-rn-active-all" exists with status "in_progress"
    And an issue "kanbus-rn-ready-all" exists with status "open"
    When I run "kanbus now --list --status all"
    Then the command should succeed
    And stdout should contain "kanbus-rn-active-all"
    And stdout should contain "kanbus-rn-ready-all"

  Scenario: Now --status open lists open issues
    Given an issue "kanbus-rn-active-open" exists with status "in_progress"
    And an issue "kanbus-rn-ready-open" exists with status "open"
    When I run "kanbus now --list --status open"
    Then the command should succeed
    And stdout should contain "kanbus-rn-ready-open"
    And stdout should not contain "kanbus-rn-active-open"

  Scenario: Now --status accepts comma-separated statuses
    Given an issue "kanbus-rn-active-multi" exists with status "in_progress"
    And an issue "kanbus-rn-ready-multi" exists with status "open"
    And an issue "kanbus-rn-closed-multi" exists with status "closed"
    When I run "kanbus now --list --status in_progress,open"
    Then the command should succeed
    And stdout should contain "kanbus-rn-active-multi"
    And stdout should contain "kanbus-rn-ready-multi"
    And stdout should not contain "kanbus-rn-closed-multi"

  Scenario: Named Now issue is shown even when it is not in progress
    Given an issue "kanbus-rn-named-open" exists with status "open"
    When I run "kanbus now kanbus-rn-named-open --list --no-recursive"
    Then the command should succeed
    And stdout should contain "kanbus-rn-named-open"
