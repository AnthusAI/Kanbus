Feature: Host-controlled issue identifier display
  As an application developer
  I want to decide how issue identifiers read in the shared Kanbus components
  So that my application can show quiet readable paths instead of truncated codes

  Scenario: Without a host formatter identifiers keep the existing format
    Given a host application with article and task issues
    When the host renders the "refined-newsprint" board with issue ids "without" a host formatter
    Then the "card" ids read "ARTICLE-1, ARTICLE-3, ARTICLE-2"
    And the "status tree" ids read "ARTICLE-1, ARTICLE-2, ARTICLE-3"
    And the "detail panel" ids read "article-1"
    And the "task detail heading" ids read "ARTICLE-1, ARTICLE-2"
    And the "card" ids carry no host format marker
    And the descendant link is labelled "Navigate to ARTICLE-2: Second article"

  Scenario: A host formatter output appears verbatim on every surface
    Given a host application with article and task issues
    When the host renders the "refined-newsprint" board with issue ids "with" a host formatter
    Then the "card" ids read "articles/Agent-Software-Factory-article-1, articles/Agent-Software-Factory-article-3, articles/Agent-Software-Factory-article-2"
    And the "status tree" ids read "articles/Agent-Software-Factory-article-1, articles/Agent-Software-Factory-article-2, articles/Agent-Software-Factory-article-3"
    And the "detail panel" ids read "articles/Agent-Software-Factory-article-1"
    And the "task detail heading" ids read "articles/Agent-Software-Factory-article-1, articles/Agent-Software-Factory-article-2"
    And the "card" ids carry the host format marker
    And the "status tree" ids carry the host format marker
    And the "detail panel" ids carry the host format marker
    And the descendant link is labelled "Navigate to articles/Agent-Software-Factory-article-2: Second article"

  Scenario Outline: Editorial themes do not uppercase host formatted identifiers
    Given a host application with article and task issues
    When the host renders the "<theme>" board with issue ids "with" a host formatter
    Then the host formatted card ids are not uppercase, are monospaced and are not truncated

    Examples:
      | theme             |
      | refined-newsprint |
      | newspaper-gothic  |
