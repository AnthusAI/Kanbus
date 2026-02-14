Feature: Cache invalidation

  Scenario: Cache is created on first run
    Given a Kanbus project with issues but no cache file
    When any kanbus command is run
    Then a cache file should be created in project/.cache/index.json

  Scenario: Cache ignores non-issue files
    Given a Kanbus project with issues but no cache file
    And a non-issue file exists in the issues directory
    When any kanbus command is run
    Then a cache file should be created in project/.cache/index.json

  Scenario: Cache is used when issue files have not changed
    Given a Kanbus project with a valid cache
    When any kanbus command is run
    Then the cache should be loaded without re-scanning issue files

  Scenario: Cache is rebuilt when an issue file changes
    Given a Kanbus project with a valid cache
    When an issue file is modified (mtime changes)
    And any kanbus command is run
    Then the cache should be rebuilt from the issue files

  Scenario: Cache is rebuilt when an issue file is added
    Given a Kanbus project with a valid cache
    When a new issue file appears in the issues directory
    And any kanbus command is run
    Then the cache should be rebuilt

  Scenario: Cache is rebuilt when an issue file is deleted
    Given a Kanbus project with a valid cache
    When an issue file is removed from the issues directory
    And any kanbus command is run
    Then the cache should be rebuilt

  Scenario: Cache preserves parent, labels, and reverse dependencies
    Given a Kanbus project with cacheable issue metadata
    When the cache is loaded
    Then the cached index should include parent relationships
    And the cached index should include label indexes
    And the cached index should include reverse dependencies
