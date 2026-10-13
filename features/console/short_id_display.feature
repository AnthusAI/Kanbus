@console
Feature: Console short ID display
  As a Kanbus console user
  I want issue IDs displayed as short lowercase keys that stay unique in view
  So that I can identify issues without reading full hashes

  Scenario: Board cards show 4-character lowercase short IDs by default
    Given the console is open
    And no issues exist in the console
    And the console has only these issues:
      | id                | title     | status | priority | created_at               | updated_at               |
      | kanbus-a1b2c3d4e5 | Alpha     | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
      | kanbus-9f8e7d6c5b | Zulu      | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
    When I switch to the "Tasks" tab
    Then the issue card "Alpha" shows the short ID "kanbus-a1b2"
    And the issue card "Zulu" shows the short ID "kanbus-9f8e"

  Scenario: Colliding short IDs are widened until unique in view
    Given the console is open
    And no issues exist in the console
    And the console has only these issues:
      | id                  | title   | status | priority | created_at               | updated_at               |
      | kanbus-aaaabbbb     | First   | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
      | kanbus-aaaacccc     | Second  | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
    When I switch to the "Tasks" tab
    Then the issue card "First" shows the short ID "kanbus-aaaab"
    And the issue card "Second" shows the short ID "kanbus-aaaac"

  Scenario: Widths re-run when the visible set shrinks
    Given the console is open
    And no issues exist in the console
    And the console has only these issues:
      | id              | title    | status | priority | created_at               | updated_at               |
      | kanbus-dddd1111 | Delta 1  | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
      | kanbus-dddd2222 | Delta 2  | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
    When I switch to the "Tasks" tab
    Then the issue card "Delta 1" shows the short ID "kanbus-dddd1"
    When I search for "Delta 1"
    Then the issue card "Delta 1" shows the short ID "kanbus-dddd"

  Scenario: Short IDs are displayed lowercase
    Given the console is open
    And no issues exist in the console
    And the console has only these issues:
      | id            | title     | status | priority | created_at               | updated_at               |
      | kanbus-F1E2D3 | Upper 1   | open   | 2        | 2026-01-01T00:00:00.000Z | 2026-01-02T00:00:00.000Z |
    When I switch to the "Tasks" tab
    Then the issue card "Upper 1" shows the short ID "kanbus-f1e2"
