Feature: Issue dependencies
  As a Taskulus user
  I want to manage dependencies between issues
  So that blocked work is tracked and cycles are prevented

  Scenario: Add a blocked-by dependency                                       
    Given a Taskulus project with default configuration                       
    And issues "tsk-parent" and "tsk-child" exist                             
    When I run "tsk dep add tsk-child --blocked-by tsk-parent"                
    Then the command should succeed                                           
    And issue "tsk-child" should depend on "tsk-parent" with type "blocked-by"

  Scenario: Add a relates-to dependency
    Given a Taskulus project with default configuration
    And issues "tsk-left" and "tsk-right" exist
    When I run "tsk dep add tsk-left --relates-to tsk-right"
    Then the command should succeed
    And issue "tsk-left" should depend on "tsk-right" with type "relates-to"

  Scenario: Remove a dependency
    Given a Taskulus project with default configuration
    And issues "tsk-left" and "tsk-right" exist
    And issue "tsk-left" depends on "tsk-right" with type "blocked-by"
    When I run "tsk dep remove tsk-left --blocked-by tsk-right"
    Then the command should succeed
    And issue "tsk-left" should not depend on "tsk-right" with type "blocked-by"

  Scenario: Remove a relates-to dependency
    Given a Taskulus project with default configuration
    And issues "tsk-left" and "tsk-right" exist
    And issue "tsk-left" depends on "tsk-right" with type "relates-to"
    When I run "tsk dep remove tsk-left --relates-to tsk-right"
    Then the command should succeed
    And issue "tsk-left" should not depend on "tsk-right" with type "relates-to"

  Scenario: Reject dependency cycles
    Given a Taskulus project with default configuration
    And issues "tsk-a" and "tsk-b" exist
    And issue "tsk-a" depends on "tsk-b" with type "blocked-by"
    And a non-issue file exists in the issues directory
    When I run "tsk dep add tsk-b --blocked-by tsk-a"
    Then the command should fail with exit code 1
    And stderr should contain "cycle detected"

  Scenario: Ready query excludes blocked issues
    Given a Taskulus project with default configuration
    And issues "tsk-ready" and "tsk-blocked" exist
    And issue "tsk-blocked" depends on "tsk-ready" with type "blocked-by"
    And a non-issue file exists in the issues directory
    When I run "tsk ready"
    Then stdout should contain "tsk-ready"
    And stdout should not contain "tsk-blocked"

  Scenario: Ready output includes project paths when multiple projects exist
    Given a repository with multiple projects and issues
    When I run "tsk ready"
    Then stdout should contain "alpha/project tsk-alpha"
    And stdout should contain "beta/project tsk-beta"

  Scenario: Ready output includes project paths for local-only issues in multi-project repositories
    Given a repository with multiple projects and local issues
    When I run "tsk ready --local-only"
    Then stdout should contain "alpha/project tsk-alpha-local"
    And stdout should not contain "beta/project tsk-beta"

  Scenario: Ready output includes external project paths from dotfile
    Given a repository with a .taskulus file referencing another project
    When I run "tsk ready"
    Then stdout should contain the external project path for "tsk-external"

  Scenario: Dependency add requires a target
    Given a Taskulus project with default configuration
    And issues "tsk-child" and "tsk-parent" exist
    When I run "tsk dep add tsk-child"
    Then the command should fail with exit code 1
    And stderr should contain "dependency target is required"

  Scenario: Dependency remove requires a target
    Given a Taskulus project with default configuration
    And issues "tsk-child" and "tsk-parent" exist
    When I run "tsk dep remove tsk-child"
    Then the command should fail with exit code 1
    And stderr should contain "dependency target is required"

  Scenario: Invalid dependency type is rejected         
    Given a Taskulus project with default configuration 
    And issues "tsk-left" and "tsk-right" exist         
    When I add an invalid dependency type               
    Then the command should fail with exit code 1       
    And stderr should contain "invalid dependency type"

  Scenario: Add dependency fails for missing issue
    Given a Taskulus project with default configuration
    And an issue "tsk-parent" exists
    When I run "tsk dep add tsk-missing --blocked-by tsk-parent"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Remove dependency fails for missing issue
    Given a Taskulus project with default configuration
    When I run "tsk dep remove tsk-missing --blocked-by tsk-parent"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Adding an existing dependency is idempotent
    Given a Taskulus project with default configuration
    And issues "tsk-left" and "tsk-right" exist
    And issue "tsk-left" depends on "tsk-right" with type "blocked-by"
    When I run "tsk dep add tsk-left --blocked-by tsk-right"
    Then the command should succeed
    And issue "tsk-left" should have 1 dependency

  Scenario: Ready fails without a project
    Given an empty git repository
    When I run "tsk ready"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Ready fails when dotfile references a missing path
    Given a repository with a .taskulus file referencing a missing path
    When I run "tsk ready"
    Then the command should fail with exit code 1
    And stderr should contain "taskulus path not found"

  Scenario: Ready includes local issues
    Given a Taskulus project with default configuration
    And a local issue "tsk-local" exists
    When I run "tsk ready"
    Then stdout should contain "tsk-local"

  Scenario: Ready excludes local issues when requested
    Given a Taskulus project with default configuration
    And issues "tsk-shared" and "tsk-other" exist
    And a local issue "tsk-local" exists
    When I run "tsk ready --no-local"
    Then stdout should contain "tsk-shared"
    And stdout should not contain "tsk-local"

  Scenario: Ready lists only local issues when requested
    Given a Taskulus project with default configuration
    And issues "tsk-shared" and "tsk-local" exist
    And a local issue "tsk-local" exists
    When I run "tsk ready --local-only"
    Then stdout should contain "tsk-local"
    And stdout should not contain "tsk-shared"

  Scenario: Adding a dependency with shared downstream succeeds
    Given a Taskulus project with default configuration
    And issues "tsk-a" and "tsk-b" exist
    And issues "tsk-c" and "tsk-d" exist
    And issue "tsk-a" depends on "tsk-b" with type "blocked-by"
    And issue "tsk-b" depends on "tsk-d" with type "blocked-by"
    And issue "tsk-c" depends on "tsk-d" with type "blocked-by"
    When I run "tsk dep add tsk-a --blocked-by tsk-c"
    Then the command should succeed

  Scenario: Ready filtering rejects local-only conflicts
    Given a Taskulus project with default configuration
    When I run "tsk ready --local-only --no-local"
    Then the command should fail with exit code 1
    And stderr should contain "local-only conflicts with no-local"
