Feature: Wiki list search render JSON and limit flags
  As an agent or script consumer
  I want machine-readable wiki CLI output
  So that I can discover and render wiki pages programmatically

  Scenario: Wiki list human output is unchanged without flags
    Given a Kanbus project with default configuration
    And a wiki page "a.md" with content "A"
    And a wiki page "b.md" with content "B"
    And a wiki page "c.md" with content "C"
    When I run "kanbus wiki list"
    Then the command should succeed
    And stdout should contain "project/wiki/a.md"
    And stdout should contain "project/wiki/b.md"
    And stdout should contain "project/wiki/c.md"

  Scenario: Wiki list caps human output with --limit
    Given a Kanbus project with default configuration
    And a wiki page "a.md" with content "A"
    And a wiki page "b.md" with content "B"
    And a wiki page "c.md" with content "C"
    When I run "kanbus wiki list --limit 2"
    Then the command should succeed
    And stdout should contain "project/wiki/a.md"
    And stdout should contain "project/wiki/b.md"
    And stdout should not contain "project/wiki/c.md"

  Scenario: Wiki list emits JSON with --json
    Given a Kanbus project with default configuration
    And a wiki page "a.md" with content "A"
    And a wiki page "b.md" with content "B"
    When I run "kanbus wiki list --json"
    Then the command should succeed
    And stdout should be valid JSON
    And stdout should contain "\"count\": 4"
    And JSON field "pages" should contain "project/wiki/a.md"
    And JSON field "pages" should contain "project/wiki/b.md"

  Scenario: Wiki list JSON respects --limit
    Given a Kanbus project with default configuration
    And a wiki page "a.md" with content "A"
    And a wiki page "b.md" with content "B"
    And a wiki page "c.md" with content "C"
    When I run "kanbus wiki list --json --limit 2"
    Then the command should succeed
    And stdout should be valid JSON
    And stdout should contain "\"count\": 2"
    And JSON field "pages" should contain "project/wiki/a.md"
    And JSON field "pages" should contain "project/wiki/b.md"
    And JSON field "pages" should not contain "project/wiki/c.md"

  Scenario: Wiki search human zero results is unchanged
    Given a Kanbus project with default configuration
    And a wiki page "indexed.md" with content "Indexed page"
    When I run "kanbus wiki search nomatch-unique-xyz"
    Then the command should succeed
    And stdout should contain "0 results"

  Scenario: Wiki search JSON reports zero matches without human summary
    Given a Kanbus project with default configuration
    And a wiki page "indexed.md" with content "Indexed page"
    When I run "kanbus wiki search nomatch-unique-xyz --json"
    Then the command should succeed
    And stdout should be valid JSON
    And JSON field "query" should equal "nomatch-unique-xyz"
    And stdout should contain "\"count\": 0"
    And JSON field "pages" should be empty
    And stdout should not contain "0 results"

  Scenario: Wiki search caps human output with --limit
    Given a Kanbus project with default configuration
    And a wiki page "concepts/alpha.md" with content:
      """
      # Alpha concept
      Details about alpha.
      """
    And a wiki page "concepts/beta.md" with content:
      """
      # Beta concept
      Details about beta.
      """
    When I run "kanbus wiki search concept --limit 1"
    Then the command should succeed
    And stdout should contain "project/wiki/concepts/alpha.md"
    And stdout should not contain "project/wiki/concepts/beta.md"

  Scenario: Wiki search JSON respects --limit
    Given a Kanbus project with default configuration
    And a wiki page "concepts/alpha.md" with content:
      """
      # Alpha concept
      Details about alpha.
      """
    And a wiki page "concepts/beta.md" with content:
      """
      # Beta concept
      Details about beta.
      """
    When I run "kanbus wiki search concept --json --limit 1"
    Then the command should succeed
    And stdout should be valid JSON
    And stdout should contain "\"count\": 1"
    And JSON field "pages" should contain "project/wiki/concepts/alpha.md"
    And JSON field "pages" should not contain "project/wiki/concepts/beta.md"

  Scenario: Wiki search missing wiki directory still succeeds in human mode
    Given a Kanbus project with default configuration
    And the wiki directory does not exist
    When I run "kanbus wiki search anything"
    Then the command should succeed
    And stdout should contain "0 results"

  Scenario: Wiki search missing wiki directory succeeds in JSON mode
    Given a Kanbus project with default configuration
    And the wiki directory does not exist
    When I run "kanbus wiki search anything --json"
    Then the command should succeed
    And stdout should be valid JSON
    And JSON field "query" should equal "anything"
    And stdout should contain "\"count\": 0"
    And JSON field "pages" should be empty

  Scenario: Wiki render human output is unchanged without flags
    Given a Kanbus project with default configuration
    And 3 open tasks and 2 closed tasks exist
    And a wiki page "status.md" with content:
      """
      Open: {{ count(status="open") }}
      Closed: {{ count(status="closed") }}
      """
    When I run "kanbus wiki render status.md"
    Then the command should succeed
    And stdout should contain "Open: 3"
    And stdout should contain "Closed: 2"

  Scenario: Wiki render emits JSON with --json
    Given a Kanbus project with default configuration
    And 3 open tasks and 2 closed tasks exist
    And a wiki page "status.md" with content:
      """
      Open: {{ count(status="open") }}
      Closed: {{ count(status="closed") }}
      """
    When I run "kanbus wiki render status.md --json"
    Then the command should succeed
    And stdout should be valid JSON
    And JSON field "path" should equal "project/wiki/status.md"
    And JSON field "rendered" should contain "Open: 3"
    And JSON field "rendered" should contain "Closed: 2"

  Scenario: Wiki render JSON keeps warnings on stderr
    Given a Kanbus project with default configuration
    And a wiki page "warn.md" with content:
      """
      # Warn page
      Link: [missing](concepts/missing.md)
      Open: {{ count(status="open") }}
      """
    When I run "kanbus wiki render warn.md --json"
    Then the command should succeed
    And stdout should be valid JSON
    And JSON field "rendered" should contain "Open:"
    And stderr should contain "warning:"
    And stderr should contain "broken wiki link"
