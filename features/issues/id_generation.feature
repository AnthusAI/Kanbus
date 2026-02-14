Feature: Issue ID generation
  As a Kanbus user
  I want issue IDs that are unique and predictable
  So that I can reference issues reliably

  Scenario: Generated IDs follow the project-key-uuid format
    Given a project with project key "kanbus"
    When I generate an issue ID
    Then the ID should match the pattern "kanbus-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

  Scenario: Generated IDs are unique across multiple creations
    Given a project with project key "kanbus"
    When I generate 100 issue IDs
    Then all 100 IDs should be unique

  Scenario: ID generation handles collision with existing issues
    Given a project with an existing issue "kanbus-11111111-2222-3333-4444-555555555555"
    When I generate an issue ID
    Then the ID should not be "kanbus-11111111-2222-3333-4444-555555555555"
    And the ID should match the pattern "kanbus-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

  Scenario: ID generation fails after repeated collisions
    Given a project with an existing issue "kanbus-11111111-2222-3333-4444-555555555555"
    And the UUID generator always returns "11111111-2222-3333-4444-555555555555"
    When I attempt to generate an issue ID
    Then ID generation should fail with "unable to generate unique id after 10 attempts"
