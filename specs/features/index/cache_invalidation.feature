@wip
Feature: Cache invalidation

  @wip
  Scenario: Cache is created on first run
    Given a Taskulus project with issues but no cache file
    When any tsk command is run
    Then a cache file should be created in project/.cache/index.json

  @wip
  Scenario: Cache is used when issue files have not changed
    Given a Taskulus project with a valid cache
    When any tsk command is run
    Then the cache should be loaded without re-scanning issue files

  @wip
  Scenario: Cache is rebuilt when an issue file changes
    Given a Taskulus project with a valid cache
    When an issue file is modified (mtime changes)
    And any tsk command is run
    Then the cache should be rebuilt from the issue files

  @wip
  Scenario: Cache is rebuilt when an issue file is added
    Given a Taskulus project with a valid cache
    When a new issue file appears in the issues directory
    And any tsk command is run
    Then the cache should be rebuilt

  @wip
  Scenario: Cache is rebuilt when an issue file is deleted
    Given a Taskulus project with a valid cache
    When an issue file is removed from the issues directory
    And any tsk command is run
    Then the cache should be rebuilt
