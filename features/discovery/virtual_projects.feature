Feature: Virtual project discovery
  As a cybernetic developer
  I want to map external project corpora into my Kanbus board
  So that I can manage work across multiple projects from one place

  Scenario: Virtual projects are listed from configuration
    Given a Kanbus project with virtual projects configured
    When I run "kanbus list"
    Then issues from all virtual projects should be listed
    And issues from the current project should be listed

  Scenario: Virtual project issues include project label
    Given a Kanbus project with virtual projects configured
    When I run "kanbus list"
    Then each issue should display its source project label

  Scenario: Virtual projects include local issues from mapped projects
    Given a Kanbus project with virtual projects configured
    And a virtual project has local issues
    When I run "kanbus list"
    Then local issues from the virtual project should be listed

  Scenario: Virtual project with missing path fails at load time
    Given a Kanbus project with a virtual project pointing to a missing path
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "virtual project path not found"

  Scenario: Virtual project without issues directory fails gracefully
    Given a Kanbus project with a virtual project pointing to a directory without issues
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "issues directory not found"

  Scenario: Duplicate virtual project labels are rejected
    Given a Kanbus project with duplicate virtual project labels
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "duplicate virtual project label"

  Scenario: Virtual project label cannot collide with current project key
    Given a Kanbus project with a virtual project label matching the project key
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "virtual project label conflicts with project key"

  Scenario: Legacy external_projects config is rejected
    Given a Kanbus repository with a .kanbus.yml file using external_projects
    When the configuration is loaded
    Then the command should fail with exit code 1
    And stderr should contain "external_projects has been replaced by virtual_projects"
