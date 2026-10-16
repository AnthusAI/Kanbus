Feature: Embed a configured issue collection
  As an application developer
  I want the shared Kanbus components to use my issue types and workflows
  So that my application can own its data access and navigation

  Scenario: Display a configured workflow in the existing board
    Given a host application with article and task issues
    When the host renders an article board
    Then the board columns are "Draft, Editorial review, Published"
    And the displayed issue identifiers are "article-1, article-2, article-3"
    And the collection has made no API requests

  Scenario: Combine standard and typed custom filters in a list
    Given a host application with article and task issues
    When the host renders a list with query
      """
      {"type":"article","status":"draft","assignee":"alex","label":"newsletter","parent":"series-","search":"ARRANGE","fields":[{"field":"custom.score","operator":"lte","value":10}]}
      """
    Then the displayed issue identifiers are "article-1"
    And the collection has made no API requests

  Scenario Outline: Custom comparisons preserve scalar types and exclude missing fields
    Given a host application with article and task issues
    When the host filters articles with query <query>
    Then the matching issue identifiers are <identifiers>

    Examples:
      | query                                                                        | identifiers               |
      | {"fields":[{"field":"custom.score","operator":"eq","value":8}]}                 | "article-1"               |
      | {"fields":[{"field":"custom.score","operator":"eq","value":"8"}]}               | "article-2"               |
      | {"fields":[{"field":"custom.score","operator":"gt","value":8}]}                 | "article-3"               |
      | {"fields":[{"field":"custom.score","operator":"gte","value":8}]}                | "article-1, article-3"    |
      | {"fields":[{"field":"custom.score","operator":"lt","value":12}]}                | "article-1"               |
      | {"fields":[{"field":"custom.ready","operator":"eq","value":true}]}              | "article-1"               |
      | {"fields":[{"field":"custom.ready","operator":"gte","value":false}]}            | ""                        |
      | {"fields":[{"field":"custom.missing","operator":"eq","value":0}]}               | ""                        |
      | {"fields":[{"field":"custom.toString","operator":"eq","value":"function"}]}     | ""                        |

  Scenario: Selecting an issue preserves host navigation and the original record
    Given a host application with article and task issues
    When the host renders an article board
    And I select issue "article-1" with the keyboard
    Then the host receives the original issue including its custom fields
    And the host route and outside content remain unchanged

  Scenario: A host update moves a record between configured columns
    Given a host application with article and task issues
    When the host renders an article board
    And the host supplies issue "article-1" with status "review"
    Then issue "article-1" appears in column "review"

  Scenario: An empty filtered list is explained by the host message
    Given a host application with article and task issues
    When the host renders a list with query
      """
      {"assignee":"nobody"}
      """
    Then the collection displays "No matching articles"

  Scenario: The standalone board remains available
    Given a host application with article and task issues
    When the host renders the existing standalone Board directly
    Then the board columns are "Open"
    And the displayed issue identifiers are "task-1"
