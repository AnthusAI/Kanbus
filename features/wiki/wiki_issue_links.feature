Feature: Wiki and issue cross-linking
  As a Kanbus user
  I want relative links between issue descriptions, comments, and wiki articles
  So that I can navigate between documentation and issues like Confluence links to Jira

  Scenario: Description links to wiki page
    Given a Kanbus project with default configuration
    And a wiki page "roadmap.md" with content:
      """
      # Roadmap
      Future plans here.
      """
    And an issue "kanbus-links" exists with title "Cross-link test"
    And issue "kanbus-links" has description "See [roadmap](roadmap.md) for plans"
    When I run "kanbus show kanbus-links"
    Then the command should succeed
    And the rendered description should contain a link to wiki path "roadmap.md"

  Scenario: Description links to nested wiki page
    Given a Kanbus project with default configuration
    And a wiki page "docs/arch.md" with content:
      """
      # Architecture
      System design here.
      """
    And an issue "kanbus-nested" exists with title "Arch link"
    And issue "kanbus-nested" has description containing:
      """
      See [architecture](docs/arch.md) for design.
      """
    When I run "kanbus show kanbus-nested"
    Then the command should succeed
    And the rendered description should contain a link to wiki path "docs/arch.md"

  Scenario: Comment links to wiki page
    Given a Kanbus project with default configuration
    And a wiki page "notes.md" with content:
      """
      # Notes
      Meeting notes here.
      """
    And an issue "kanbus-comment-link" exists with title "With comment"
    And the current user is "dev@example.com"
    And a comment on issue "kanbus-comment-link" contains "[notes](notes.md)"
    When I run "kanbus show kanbus-comment-link"
    Then the command should succeed
    And the rendered comments should contain a link to wiki path "notes.md"

  Scenario: Wiki page links to issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-abc" exists with title "Target issue"
    And a wiki page "references.md" with content:
      """
      See [kanbus-abc](kanbus-abc) for details.
      """
    When I run "kanbus wiki render project/wiki/references.md"
    Then the command should succeed
    And the rendered wiki should contain a link to issue "kanbus-abc"

  Scenario: Wiki template links to issue by id
    Given a Kanbus project with default configuration
    And an issue "kanbus-epic01" exists with title "Main epic"
    And a wiki page "linked.md" with content:
      """
      {% set item = issue("kanbus-epic01") %}
      Epic: [{{ item.title }}]({{ item.id }})
      """
    When I run "kanbus wiki render project/wiki/linked.md"
    Then the command should succeed
    And stdout should contain "Epic: [Main epic](kanbus-epic01)"
    And the rendered wiki should contain a link to issue "kanbus-epic01"

  Scenario: Description has dynamic count
    Given a Kanbus project with default configuration
    And 3 open tasks exist
    And an issue "kanbus-dynamic" exists with title "Dynamic test"
    And issue "kanbus-dynamic" has description containing:
      """
      Open: {{ count(status="open") }}
      """
    When I run "kanbus show kanbus-dynamic"
    Then the command should succeed
    And the rendered description should contain "Open: 4"

  Scenario: Comment has dynamic query
    Given a Kanbus project with default configuration
    And open tasks "Alpha" and "Beta" exist
    And an issue "kanbus-query" exists with title "Query test"
    And the current user is "dev@example.com"
    And a comment on issue "kanbus-query" contains:
      """
      {% for i in query(status="open", sort="title") %}
      - {{ i.title }}
      {% endfor %}
      """
    When I run "kanbus show kanbus-query"
    Then the command should succeed
    And the rendered comments should contain "- Alpha"
    And the rendered comments should contain "- Beta"
