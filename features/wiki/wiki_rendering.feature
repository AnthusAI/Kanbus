Feature: Wiki rendering
  Scenario: Render a wiki page with a simple query
    Given a Kanbus project with default configuration
    And 3 open tasks and 2 closed tasks exist
    And a wiki page "status.md" with content:
      """
      Open: {{ count(status="open") }}
      Closed: {{ count(status="closed") }}
      """
    When I run "kanbus wiki render project/wiki/status.md"
    Then stdout should contain "Open: 3"
    And stdout should contain "Closed: 2"

  Scenario: Render a wiki page with a for loop
    Given a Kanbus project with default configuration
    And open tasks "Alpha" and "Beta" exist
    And a wiki page "tasks.md" with content:
      """
      {% for issue in query(status="open", sort="title") %}
      - {{ issue.title }}
      {% endfor %}
      """
    When I run "kanbus wiki render project/wiki/tasks.md"
    Then stdout should contain "- Alpha"
    And stdout should contain "- Beta"
    And "Alpha" should appear before "Beta" in the output

  Scenario: Render a wiki page sorted by priority
    Given a Kanbus project with default configuration
    And open tasks "Urgent" and "Later" exist with priorities 1 and 3
    And a wiki page "priority.md" with content:
      """
      {% for issue in query(status="open", sort="priority") %}
      - {{ issue.title }}
      {% endfor %}
      """
    When I run "kanbus wiki render project/wiki/priority.md"
    Then stdout should contain "- Urgent"
    And stdout should contain "- Later"
    And "Urgent" should appear before "Later" in the output

  Scenario: Render a wiki page with type filter
    Given a Kanbus project with default configuration
    And open tasks "Alpha" and "Beta" exist
    And a wiki page "types.md" with content:
      """
      {% for issue in query(issue_type="task", status="open", sort="title") %}
      - {{ issue.title }}
      {% endfor %}
      """
    When I run "kanbus wiki render project/wiki/types.md"
    Then stdout should contain "- Alpha"
    And stdout should contain "- Beta"

  Scenario: Render a wiki page by absolute path
    Given a Kanbus project with default configuration
    And a wiki page "absolute.md" with content:
      """
      Open: {{ count(status="open") }}
      """
    When I render the wiki page "absolute.md" by absolute path
    Then stdout should contain "Open:"

  Scenario: Render a wiki page filtered by issue type
    Given a Kanbus project with default configuration
    And a "task" issue "kanbus-task" exists
    And a "bug" issue "kanbus-bug" exists
    And a wiki page "bugs.md" with content:
      """
      {% for issue in query(issue_type="bug", status="open") %}
      - {{ issue.id }}
      {% endfor %}
      """
    When I run "kanbus wiki render project/wiki/bugs.md"
    Then stdout should contain "- kanbus-bug"
    And stdout should not contain "- kanbus-task"

  Scenario: Render fails for invalid sort key
    Given a Kanbus project with default configuration
    And open tasks "Alpha" and "Beta" exist
    And a wiki page "invalid_sort.md" with content:
      """
      {% for issue in query(status="open", sort="unknown") %}
      - {{ issue.title }}
      {% endfor %}
      """
    When I run "kanbus wiki render project/wiki/invalid_sort.md"
    Then the command should fail with exit code 1
    And stderr should contain "invalid sort key"

  Scenario: Render fails for invalid query parameter
    Given a Kanbus project with default configuration
    And a wiki page "invalid_param.md" with content:
      """
      {{ count(status=1) }}
      """
    When I run "kanbus wiki render project/wiki/invalid_param.md"
    Then the command should fail with exit code 1
    And stderr should contain "invalid query parameter"

  Scenario: Render fails when the page is missing
    Given a Kanbus project with default configuration
    When I run "kanbus wiki render project/wiki/missing.md"
    Then the command should fail with exit code 1
    And stderr should contain "wiki page not found"

  Scenario: Render fails when project is not initialized
    Given an empty git repository
    And a raw wiki page "orphan.md" with content:
      """
      {{ count(status="open") }}
      """
    When I run "kanbus wiki render orphan.md"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Render fails for invalid template syntax
    Given a Kanbus project with default configuration
    And a wiki page "invalid_template.md" with content:
      """
      {{ 1 / 0 }}
      """
    When I run "kanbus wiki render project/wiki/invalid_template.md"
    Then the command should fail with exit code 1
    And stderr should contain "division by zero"
