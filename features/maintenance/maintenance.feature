Feature: Maintenance commands
  As a Kanbus maintainer
  I want diagnostic and maintenance commands
  So that the repository stays healthy

  Scenario: Validate project integrity
    Given a Kanbus project with default configuration
    When I run "kanbus validate"
    Then the command should succeed

  Scenario: Report project statistics
    Given a Kanbus project with default configuration
    And issues "kanbus-open" and "kanbus-closed" exist
    And issue "kanbus-closed" has status "closed"
    And a non-issue file exists in the issues directory
    When I run "kanbus stats"
    Then stdout should contain "total issues"
    And stdout should contain "open issues"
    And stdout should contain "closed issues"

  Scenario: Stats include type counts
    Given a Kanbus project with default configuration
    And issues "kanbus-task" and "kanbus-bug" exist
    And issue "kanbus-bug" has type "bug"
    When I run "kanbus stats"
    Then stdout should contain "type: task"
    And stdout should contain "type: bug"

  Scenario: Validation fails for invalid issue status
    Given a Kanbus project with default configuration
    And issues "kanbus-bad" and "kanbus-good" exist
    And issue "kanbus-bad" has status "unknown"
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "invalid status"

  Scenario: Stats fails for invalid JSON
    Given a Kanbus project with default configuration
    And an issue file contains invalid JSON
    When I run "kanbus stats"
    Then the command should fail with exit code 1
    And stderr should contain "invalid json"

  Scenario: Validation fails when issues directory is missing
    Given a Kanbus project with default configuration
    And the issues directory is missing
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "issues directory missing"

  Scenario: Validation fails when configuration path lookup fails
    Given a Kanbus project with default configuration
    And configuration path lookup will fail
    When I validate the project directly
    Then the command should fail with exit code 1
    And stderr should contain "configuration path lookup failed"

  Scenario: Validation fails for invalid issue data
    Given a Kanbus project with default configuration
    And an issue file contains invalid issue data
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "invalid issue data"

  Scenario: Validation fails for invalid JSON
    Given a Kanbus project with default configuration
    And an issue file contains invalid JSON
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "invalid json"

  Scenario: Validation fails for out-of-range priority
    Given a Kanbus project with default configuration
    And an issue file contains out-of-range priority
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "invalid priority"

  Scenario: Validation fails for unreadable issue files
    Given a Kanbus project with default configuration
    And an issue file is unreadable
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "unable to read issue"

  Scenario: Validation reports multiple issue errors                            
    Given a Kanbus project with default configuration                         
    And invalid issues exist with multiple validation errors                    
    When I run "kanbus validate"                                                   
    Then the command should fail with exit code 1                               
    And stderr should contain "unknown issue type"
    And stderr should contain "invalid status 'bogus'"
    And stderr should contain "invalid priority"
    And stderr should contain "issue id 'kanbus-mismatch' does not match filename"
    And stderr should contain "closed issues must have closed_at set"
    And stderr should contain "non-closed issues must not set closed_at"
    And stderr should contain "invalid dependency type"
    And stderr should contain "parent 'kanbus-missing' does not exist"
    And stderr should contain "dependency target 'kanbus-missing' does not exist" 
    And stderr should contain "invalid parent-child relationship"              

  Scenario: Validation reports duplicate issue ids
    Given a Kanbus project with default configuration
    And duplicate issue identifiers exist
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "duplicate issue id"

  Scenario: Workflow status collection fails without default workflow
    Given a configuration without a default workflow
    When workflow statuses are collected for issue type "task"
    Then workflow status collection should fail with "default workflow not defined"

  Scenario: Stats fails without a project
    Given an empty git repository
    When I run "kanbus stats"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Stats fails when issues directory is missing
    Given a Kanbus project with default configuration
    And the issues directory is missing
    When I run "kanbus stats"
    Then the command should fail with exit code 1
    And stderr should contain "issues directory missing"

  Scenario: Stats fails for invalid issue data
    Given a Kanbus project with default configuration
    And an issue file contains invalid issue data
    When I run "kanbus stats"
    Then the command should fail with exit code 1
    And stderr should contain "invalid issue data"

  Scenario: Validation fails without a project
    Given an empty git repository
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "project not initialized"

  Scenario: Validation fails with invalid configuration
    Given a Kanbus project with an invalid configuration containing unknown fields
    When I run "kanbus validate"
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"

  Scenario: Doctor fails with invalid configuration
    Given a Kanbus project with an invalid configuration containing unknown fields
    When I run "kanbus doctor"
    Then the command should fail with exit code 1
    And stderr should contain "unknown configuration fields"
