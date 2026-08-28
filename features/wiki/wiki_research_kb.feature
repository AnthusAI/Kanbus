Feature: Wiki research knowledge base
  As a Papyrus research pod operator
  I want the wiki CLI and templates to work as a live knowledge base
  So that project/wiki/ can replace a compiled research wiki

  Scenario: Render wiki page by short path without prefix
    Given a Kanbus project with default configuration
    And a wiki page "index.md" with content:
      """
      # Home
      Welcome to the wiki.
      """
    When I run "kanbus wiki render index"
    Then the command should succeed
    And stdout should contain "Welcome to the wiki"

  Scenario: Render wiki page by filename with md extension
    Given a Kanbus project with default configuration
    And a wiki page "index.md" with content "Index body"
    When I run "kanbus wiki render index.md"
    Then the command should succeed
    And stdout should contain "Index body"

  Scenario: Render wiki page by dot-slash relative path
    Given a Kanbus project with default configuration
    And a wiki page "dot.md" with content "Dot slash path works"
    When I run "kanbus wiki render ./dot.md"
    Then the command should succeed
    And stdout should contain "Dot slash path works"

  Scenario: Render nested wiki page by relative path
    Given a Kanbus project with default configuration
    And a wiki page "concepts/foo.md" with content "Concept page"
    When I run "kanbus wiki render concepts/foo.md"
    Then the command should succeed
    And stdout should contain "Concept page"

  Scenario: Render wiki page by canonical prefixed path
    Given a Kanbus project with default configuration
    And a wiki page "index.md" with content "Canonical path works"
    When I run "kanbus wiki render project/wiki/index.md"
    Then the command should succeed
    And stdout should contain "Canonical path works"

  Scenario: Missing wiki directory shows create hint
    Given a Kanbus project with default configuration
    And the wiki directory does not exist
    When I run "kanbus wiki render index.md"
    Then the command should fail with exit code 1
    And stderr should contain "wiki directory not found"
    And stderr should contain "kbs wiki init"

  Scenario: Missing wiki page shows not found with path
    Given a Kanbus project with default configuration
    And an empty wiki directory exists
    When I run "kanbus wiki render missing.md"
    Then the command should fail with exit code 1
    And stderr should contain "wiki page not found"
    And stderr should contain "missing.md"

  Scenario: Wiki init creates stub index page
    Given a Kanbus project with default configuration
    And the wiki directory does not exist
    When I run "kanbus wiki init"
    Then the command should succeed
    And the wiki root should be "project/wiki"
    And a wiki page "index.md" should exist with content containing "Wiki"

  Scenario: Search wiki pages by path title and body
    Given a Kanbus project with default configuration
    And a wiki page "index.md" with content:
      """
      # Home
      Overview of the pod.
      """
    And a wiki page "concepts/alpha.md" with content:
      """
      # Alpha concept
      Details about alpha.
      """
    And a wiki page "notes/beta.md" with content "Unrelated notes"
    When I run "kanbus wiki search alpha"
    Then the command should succeed
    And stdout should contain "project/wiki/concepts/alpha.md"
    And stdout should not contain "project/wiki/notes/beta.md"

  Scenario: Wiki search with empty query lists all pages
    Given a Kanbus project with default configuration
    And a wiki page "listed.md" with content "Listed in empty search"
    When I run "kanbus wiki search \"\""
    Then the command should succeed
    And stdout should contain "project/wiki/listed.md"

  Scenario: Wiki list still works after search is added
    Given a Kanbus project with default configuration
    And a wiki page "a.md" with content "A"
    And a wiki page "b.md" with content "B"
    When I run "kanbus wiki list"
    Then the command should succeed
    And stdout should contain "project/wiki/a.md"
    And stdout should contain "project/wiki/b.md"

  Scenario: Wiki template exposes short issue key
    Given a Kanbus project with default configuration
    And an issue "WIKI-650fd91d-7f3b-427e-aa7f-253b228b48d9" exists with title "Standing story"
    And a wiki page "keys.md" with content:
      """
      {% for issue in query(status="open", sort="title") %}
      key={{ issue.key }} id={{ issue.id }}
      {% endfor %}
      """
    When I run "kanbus wiki render keys.md"
    Then the command should succeed
    And stdout should contain "key=650fd9"
    And stdout should contain "id=WIKI-650fd91d-7f3b-427e-aa7f-253b228b48d9"

  Scenario: Wiki template lists accepted story references
    Given a Kanbus project with default configuration
    And a story reference "WIKI-650fd9" file "ref-a.json" with content:
      """
      {
        "id": "ref-a",
        "title": "Accepted paper",
        "url": "https://example.com/a",
        "why": "Primary source",
        "status": "accepted",
        "corpus": "papers"
      }
      """
    And a story reference "WIKI-650fd9" file "ref-b.json" with content:
      """
      {
        "id": "ref-b",
        "title": "Pending paper",
        "url": "https://example.com/b",
        "why": "Maybe later",
        "status": "pending",
        "corpus": "papers"
      }
      """
    And a wiki page "refs.md" with content:
      """
      {% for ref in references(status="accepted") %}
      - {{ ref.id }}: {{ ref.title }} ({{ ref.corpus }})
      {% endfor %}
      """
    When I run "kanbus wiki render refs.md"
    Then the command should succeed
    And stdout should contain "- ref-a: Accepted paper (papers)"
    And stdout should not contain "Pending paper"

  Scenario: Show wiki page prints raw markdown source
    Given a Kanbus project with default configuration
    And a wiki page "raw.md" with content:
      """
      # Raw page
      Template marker: {{ count(status="open") }}
      """
    When I run "kanbus wiki show raw.md"
    Then the command should succeed
    And stdout should contain "Template marker: {{ count(status=\"open\") }}"

  Scenario: Show wiki page fails when the page does not exist
    Given a Kanbus project with default configuration
    And an empty wiki directory exists
    When I run "kanbus wiki show missing.md"
    Then the command should fail with exit code 1
    And stderr should contain "wiki page not found"
    And stderr should contain "missing.md"

  Scenario: Wiki init is idempotent when the index page already exists
    Given a Kanbus project with default configuration
    And a wiki page "index.md" with content "# Custom index"
    When I run "kanbus wiki init"
    Then the command should succeed
    And a wiki page "index.md" should exist with content containing "Custom index"

  Scenario: Wiki lint passes when internal md links resolve
    Given a Kanbus project with default configuration
    And a wiki page "concepts/alpha.md" with content "# Alpha"
    And a wiki page "index.md" with content:
      """
      See [alpha](concepts/alpha.md).
      """
    When I run "kanbus wiki lint"
    Then the command should succeed
    And stdout should contain "wiki lint: ok"

  Scenario: Wiki lint ignores external URLs and anchor-only links
    Given a Kanbus project with default configuration
    And a wiki page "index.md" with content:
      """
      [external](https://example.com/doc.md)
      [section](#local-section)
      """
    When I run "kanbus wiki lint"
    Then the command should succeed
    And stdout should contain "wiki lint: ok"

  Scenario: Wiki lint reports missing wiki directory
    Given a Kanbus project with default configuration
    And the wiki directory does not exist
    When I run "kanbus wiki lint"
    Then the command should fail with exit code 1
    And stderr should contain "wiki directory not found"
    And stderr should contain "kbs wiki init"

  Scenario: Wiki lint fails on broken relative md link
    Given a Kanbus project with default configuration
    And a wiki page "index.md" with content:
      """
      See [missing](concepts/missing.md).
      """
    When I run "kanbus wiki lint"
    Then the command should fail with exit code 1
    And stderr should contain "broken wiki link"
    And stderr should contain "concepts/missing.md"

  Scenario: Wiki check validates the wiki tree like lint
    Given a Kanbus project with default configuration
    And a wiki page "index.md" with content:
      """
      See [missing](sources/missing.md).
      """
    When I run "kanbus wiki check"
    Then the command should fail with exit code 1
    And stderr should contain "broken wiki link"
    And stderr should contain "sources/missing.md"

  Scenario: Wiki render warns on broken md link but still succeeds
    Given a Kanbus project with default configuration
    And a wiki page "warn.md" with content:
      """
      # Warn page
      Link: [missing](concepts/missing.md)
      Open: {{ count(status="open") }}
      """
    When I run "kanbus wiki render warn.md"
    Then the command should succeed
    And stdout should contain "Open:"
    And stderr should contain "warning:"
    And stderr should contain "broken wiki link"
    And stderr should contain "concepts/missing.md"

  Scenario: Wiki render cache ignores story references when the template does not call references
    Given a Kanbus project with default configuration
    And a story reference "WIKI-650fd9" file "ref-a.json" with content:
      """
      {
        "id": "ref-a",
        "title": "First accepted paper",
        "url": "https://example.com/a",
        "why": "Primary source",
        "status": "accepted",
        "corpus": "papers"
      }
      """
    And a wiki page "static.md" with content:
      """
      Static: {{ count(status="open") }}
      """
    When I run "kanbus wiki render static.md"
    Then the command should succeed
    And stdout should contain "Static:"
    And stdout should not contain "ref-a"
    Given a story reference "WIKI-650fd9" file "ref-c.json" with content:
      """
      {
        "id": "ref-c",
        "title": "Newly accepted paper",
        "url": "https://example.com/c",
        "why": "Added after first render",
        "status": "accepted",
        "corpus": "papers"
      }
      """
    When I run "kanbus wiki render static.md"
    Then the command should succeed
    And stdout should not contain "ref-c"

  Scenario: Wiki render picks up new accepted references after cache warm
    Given a Kanbus project with default configuration
    And a story reference "WIKI-650fd9" file "ref-a.json" with content:
      """
      {
        "id": "ref-a",
        "title": "First accepted paper",
        "url": "https://example.com/a",
        "why": "Primary source",
        "status": "accepted",
        "corpus": "papers"
      }
      """
    And a wiki page "live-refs.md" with content:
      """
      {% for ref in references(status="accepted") %}
      - {{ ref.id }}: {{ ref.title }}
      {% endfor %}
      """
    When I run "kanbus wiki render live-refs.md"
    Then the command should succeed
    And stdout should contain "- ref-a: First accepted paper"
    Given a story reference "WIKI-650fd9" file "ref-c.json" with content:
      """
      {
        "id": "ref-c",
        "title": "Newly accepted paper",
        "url": "https://example.com/c",
        "why": "Added after first render",
        "status": "accepted",
        "corpus": "papers"
      }
      """
    When I run "kanbus wiki render live-refs.md"
    Then the command should succeed
    And stdout should contain "- ref-c: Newly accepted paper"

  Scenario: Wiki render skips invalid story reference JSON with warning
    Given a Kanbus project with default configuration
    And a story reference "WIKI-650fd9" file "bad.json" with content:
      """
      """
    And a story reference "WIKI-650fd9" file "good.json" with content:
      """
      {
        "id": "ref-good",
        "title": "Valid accepted paper",
        "url": "https://example.com/good",
        "why": "Keeps rendering",
        "status": "accepted",
        "corpus": "papers"
      }
      """
    And a wiki page "refs-tolerant.md" with content:
      """
      {% for ref in references(status="accepted") %}
      - {{ ref.id }}: {{ ref.title }}
      {% endfor %}
      """
    When I run "kanbus wiki render refs-tolerant.md"
    Then the command should succeed
    And stdout should contain "- ref-good: Valid accepted paper"
    And stderr should contain "skipping"
    And stderr should contain "bad.json"

  Scenario: Wiki render skips malformed story reference JSON with warning
    Given a Kanbus project with default configuration
    And a story reference "WIKI-650fd9" file "broken-syntax.json" with content:
      """
      {
      """
    And a story reference "WIKI-650fd9" file "good.json" with content:
      """
      {
        "id": "ref-good",
        "title": "Valid accepted paper",
        "url": "https://example.com/good",
        "why": "Keeps rendering",
        "status": "accepted",
        "corpus": "papers"
      }
      """
    And a wiki page "refs-syntax.md" with content:
      """
      {% for ref in references(status="accepted") %}
      - {{ ref.id }}: {{ ref.title }}
      {% endfor %}
      """
    When I run "kanbus wiki render refs-syntax.md"
    Then the command should succeed
    And stdout should contain "- ref-good: Valid accepted paper"
    And stderr should contain "skipping"
    And stderr should contain "broken-syntax.json"

  Scenario: Wiki render skips non-object story reference JSON with warning
    Given a Kanbus project with default configuration
    And a story reference "WIKI-650fd9" file "array.json" with content:
      """
      []
      """
    And a story reference "WIKI-650fd9" file "good.json" with content:
      """
      {
        "id": "ref-good",
        "title": "Valid accepted paper",
        "url": "https://example.com/good",
        "why": "Keeps rendering",
        "status": "accepted",
        "corpus": "papers"
      }
      """
    And a wiki page "refs-array.md" with content:
      """
      {% for ref in references(status="accepted") %}
      - {{ ref.id }}: {{ ref.title }}
      {% endfor %}
      """
    When I run "kanbus wiki render refs-array.md"
    Then the command should succeed
    And stdout should contain "- ref-good: Valid accepted paper"
    And stderr should contain "skipping"
    And stderr should contain "array.json"
