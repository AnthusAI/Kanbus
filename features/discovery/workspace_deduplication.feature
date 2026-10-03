Feature: Workspace issue deduplication
  As a Kanbus user running read commands from a workspace root
  I want issues discovered across nested projects and git worktrees to be deduplicated by identity
  So that every issue appears exactly once with the most recently changed version

  Identity: the issue's own identity as Kanbus keys it, the issue `id` field.
  Titles, file paths, and project locations are not identity.

  Recency: "most recently changed" is decided by the issue's `updated_at` field,
  not the underlying issue file's mtime. The write gate maintains `updated_at` on
  every mutation, it travels with the issue data, and it is stable across git
  worktree operations, clones, and checkouts. File mtimes are not reliable:
  checking out, copying, restoring, or syncing issue files rewrites mtimes without
  changing the issue, and different filesystems report mtimes differently. This
  matches the existing Beads compatibility dedupe, which keeps the record with the
  largest `updated_at`.

  Tie-break: when copies of the same identity have equal `updated_at`, the copy
  whose serialized issue record is lexicographically greater wins. This is fully
  deterministic and independent of project discovery order or filesystem
  enumeration order. Byte-identical copies collapse to a single entry.

  Winners are placed at the position of the first occurrence of that identity in
  the discovered list, so list ordering is unchanged apart from removed
  duplicates. Distinct issues are never merged; only copies of the same identity
  collapse.

  Scenario: Same issue in a main checkout plus two worktrees appears once
    Given a workspace root containing a repository with a committed Kanbus project and two linked git worktrees
    And the copy in one worktree was changed most recently
    When I run "kanbus list"
    Then the issue appears exactly once
    And the listed entry is the most recently changed version of the issue

  Scenario: Distinct issues are never merged
    Given a workspace root containing two Kanbus projects with distinct issues
    When I run "kanbus list"
    Then each distinct issue appears exactly once

  Scenario: Ties resolve deterministically
    Given a workspace root containing a repository and a linked worktree with tied copies of the same issue
    When I run "kanbus list"
    Then the issue appears exactly once
    And the deterministic tie-break winner is listed

  Scenario: Single-project listing is unchanged
    Given a single Kanbus project with one issue and no duplicate copies
    When I run "kanbus list"
    Then the single-project listing shows the issue exactly once

  Scenario: Parent folder of many projects and worktrees yields one row per identity
    Given a workspace root containing a repository with a committed Kanbus project and two linked git worktrees
    And the copy in one worktree was changed most recently
    When I run "kanbus list"
    Then no issue identity appears more than once