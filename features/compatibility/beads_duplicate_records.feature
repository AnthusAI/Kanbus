Feature: Beads duplicate issue records
  I want duplicate Beads records to be merged automatically
  So that ambiguous IDs do not break Beads compatibility

  Scenario: Identical duplicates auto-merge
    Given a Kanbus project with beads compatibility enabled
    And a beads issue "bdx-dup" exists with status "open" and updated_at "2024-01-01T00:00:00Z"
    And a beads issue "bdx-dup" exists with status "open" and updated_at "2024-01-01T00:00:00Z"
    When I run "kanbus --beads list"
    Then stdout should contain "bdx-dup"
    And beads issues.jsonl should contain exactly 1 records with id "bdx-dup"

  Scenario: Conflicting duplicates choose latest updated_at
    Given a Kanbus project with beads compatibility enabled
    And a beads issue "bdx-dup" exists with status "open" and updated_at "2024-01-01T00:00:00Z"
    And a beads issue "bdx-dup" exists with status "closed" and updated_at "2024-02-01T00:00:00Z"
    When I run "kanbus --beads show bdx-dup"
    Then stdout should contain "Status: closed"
    And beads issues.jsonl should contain exactly 1 records with id "bdx-dup"
    And beads issues.jsonl should include status "closed" for "bdx-dup"

  Scenario: Conflicting duplicates with same updated_at prefer the larger record
    Given a Kanbus project with beads compatibility enabled
    And a beads issue "bdx-dup" exists with status "open" and updated_at "2024-01-01T00:00:00Z"
    And a beads issue "bdx-dup" exists with status "closed" and updated_at "2024-01-01T00:00:00Z"
    When I run "kanbus --beads show bdx-dup"
    Then stdout should contain "Status: closed"
    And beads issues.jsonl should contain exactly 1 records with id "bdx-dup"
