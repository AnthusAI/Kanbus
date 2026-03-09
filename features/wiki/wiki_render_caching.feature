Feature: Wiki render caching
  As a Kanbus user
  I want the rendered HTML and Markdown for wiki pages to be cached
  So that page loads are instantaneous when no data has changed

  Scenario: Rendered wiki is cached
    Given a Kanbus project with default configuration
    When I run "kanbus wiki render project/wiki/index.md"
    Then a cached rendered file should exist
    When I run "kanbus wiki render project/wiki/index.md"
    Then the command should use the cache
