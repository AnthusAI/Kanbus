Feature: Issue dependencies
  As a Kanbus user
  I want to manage dependencies between issues
  So that blocked work is tracked and cycles are prevented

  Scenario: Add a blocked-by dependency
    Given a Kanbus project with default configuration
    And issues "kanbus-parent" and "kanbus-child" exist
    When I run "kanbus dep kanbus-child blocked-by kanbus-parent"
    Then the command should succeed
    And issue "kanbus-child" should depend on "kanbus-parent" with type "blocked-by"

  Scenario: Add a relates-to dependency
    Given a Kanbus project with default configuration
    And issues "kanbus-left" and "kanbus-right" exist
    When I run "kanbus dep kanbus-left relates-to kanbus-right"
    Then the command should succeed
    And issue "kanbus-left" should depend on "kanbus-right" with type "relates-to"

  Scenario: Remove a dependency
    Given a Kanbus project with default configuration
    And issues "kanbus-left" and "kanbus-right" exist
    And issue "kanbus-left" depends on "kanbus-right" with type "blocked-by"
    When I run "kanbus dep kanbus-left remove blocked-by kanbus-right"
    Then the command should succeed
    And issue "kanbus-left" should not depend on "kanbus-right" with type "blocked-by"

  Scenario: Remove a relates-to dependency
    Given a Kanbus project with default configuration
    And issues "kanbus-left" and "kanbus-right" exist
    And issue "kanbus-left" depends on "kanbus-right" with type "relates-to"
    When I run "kanbus dep kanbus-left remove relates-to kanbus-right"
    Then the command should succeed
    And issue "kanbus-left" should not depend on "kanbus-right" with type "relates-to"

  Scenario: Reject dependency cycles
    Given a Kanbus project with default configuration
    And issues "kanbus-a" and "kanbus-b" exist
    And issue "kanbus-a" depends on "kanbus-b" with type "blocked-by"
    And a non-issue file exists in the issues directory
    When I run "kanbus dep kanbus-b blocked-by kanbus-a"
    Then the command should fail with exit code 1
    And stderr should contain "cycle detected"

  Scenario: Ready query excludes blocked issues
    Given a Kanbus project with default configuration
    And issues "kanbus-ready" and "kanbus-blocked" exist
    And issue "kanbus-blocked" depends on "kanbus-ready" with type "blocked-by"
    And a non-issue file exists in the issues directory
    When I run "kanbus ready"
    Then stdout should contain "kanbus-ready"
    And stdout should not contain "kanbus-blocked"

  Scenario: Ready listing uses a single project
    Given a Kanbus project with default configuration
    And issues "kanbus-ready" exist
    When ready issues are listed for a single project
    Then the ready list should contain "kanbus-ready"

  Scenario: Ready output includes project paths when multiple projects exist
    Given a repository with multiple projects and issues
    When I run "kanbus ready"
    Then stdout should contain "alpha/project kanbus-alpha"
    And stdout should contain "beta/project kanbus-beta"

  Scenario: Ready output includes project paths for local-only issues in multi-project repositories
    Given a repository with multiple projects and local issues
    When I run "kanbus ready --local-only"
    Then stdout should contain "alpha/project kanbus-alpha-local"
    And stdout should not contain "beta/project kanbus-beta"

  Scenario: Ready output includes external project paths from dotfile
    Given a repository with a .kanbus.yml file referencing another project
    When I run "kanbus ready"
    Then stdout should contain the external project path for "kanbus-external"

  Scenario: Dependency add requires a target
    Given a Kanbus project with default configuration
    And issues "kanbus-child" and "kanbus-parent" exist
    When I run "kanbus dep kanbus-child blocked-by"
    Then the command should fail with exit code 1
    And stderr should contain "dependency target is required"

  Scenario: Dependency remove requires a target
    Given a Kanbus project with default configuration
    And issues "kanbus-child" and "kanbus-parent" exist
    When I run "kanbus dep kanbus-child remove blocked-by"
    Then the command should fail with exit code 1
    And stderr should contain "dependency target is required"

  Scenario: Invalid dependency type is rejected         
    Given a Kanbus project with default configuration 
    And issues "kanbus-left" and "kanbus-right" exist         
    When I add an invalid dependency type               
    Then the command should fail with exit code 1       
    And stderr should contain "invalid dependency type"

  Scenario: Add dependency fails for missing issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-parent" exists
    When I run "kanbus dep kanbus-missing blocked-by kanbus-parent"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Remove dependency fails for missing issue
    Given a Kanbus project with default configuration
    When I run "kanbus dep kanbus-missing remove blocked-by kanbus-parent"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Adding an existing dependency is idempotent
    Given a Kanbus project with default configuration
    And issues "kanbus-left" and "kanbus-right" exist
    And issue "kanbus-left" depends on "kanbus-right" with type "blocked-by"
    When I run "kanbus dep kanbus-left blocked-by kanbus-right"
    Then the command should succeed
    And issue "kanbus-left" should have 1 dependency

  Scenario: Ready fails without a project
    Given an empty git repository
    When I run "kanbus ready"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Ready fails when dotfile references a missing path
    Given a repository with a .kanbus.yml file referencing a missing path
    When I run "kanbus ready"
    Then the command should fail with exit code 1
    And stderr should contain "virtual project path not found"

  Scenario: Ready includes local issues
    Given a Kanbus project with default configuration
    And a local issue "kanbus-local" exists
    When I run "kanbus ready"
    Then stdout should contain "kanbus-local"

  Scenario: Ready excludes local issues when requested
    Given a Kanbus project with default configuration
    And issues "kanbus-shared" and "kanbus-other" exist
    And a local issue "kanbus-local" exists
    When I run "kanbus ready --no-local"
    Then stdout should contain "kanbus-shared"
    And stdout should not contain "kanbus-local"

  Scenario: Ready lists only local issues when requested
    Given a Kanbus project with default configuration
    And issues "kanbus-shared" and "kanbus-local" exist
    And a local issue "kanbus-local" exists
    When I run "kanbus ready --local-only"
    Then stdout should contain "kanbus-local"
    And stdout should not contain "kanbus-shared"

  Scenario: Adding a dependency with shared downstream succeeds
    Given a Kanbus project with default configuration
    And issues "kanbus-a" and "kanbus-b" exist
    And issues "kanbus-c" and "kanbus-d" exist
    And issue "kanbus-a" depends on "kanbus-b" with type "blocked-by"
    And issue "kanbus-b" depends on "kanbus-d" with type "blocked-by"
    And issue "kanbus-c" depends on "kanbus-d" with type "blocked-by"
    When I run "kanbus dep kanbus-a blocked-by kanbus-c"
    Then the command should succeed

  Scenario: Ready filtering rejects local-only conflicts
    Given a Kanbus project with default configuration
    When I run "kanbus ready --local-only --no-local"
    Then the command should fail with exit code 1
    And stderr should contain "local-only conflicts with no-local"
