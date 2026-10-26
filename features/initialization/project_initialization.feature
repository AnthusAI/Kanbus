Feature: Project initialization
  As a developer starting a new project
  I want to initialize a Kanbus project directory
  So that I can begin tracking issues alongside my code

  Scenario: Initialize with default settings
    Given an empty git repository
    When I run "kanbus init"
    Then a "project" directory should exist
    And a "project/issues" directory should exist and contain only guard files
    And the file "project/wiki/index.md" should exist
    And the file "project/wiki/whats-next.md" should exist
    And the file "project/wiki/index.md" should contain "whats-next.md"
    And a ".kanbus.yml" file should be created
    And the file ".kanbus.yml" should contain "project_id:"
    And a "CONTRIBUTING_AGENT.template.md" file should be created
    And CONTRIBUTING_AGENT.template.md should contain "This is The Way."
    And CONTRIBUTING_AGENT.template.md should contain "{% for methodology in methodologies %}"
    And CONTRIBUTING_AGENT.template.md should contain "Agent provenance metadata"
    And CONTRIBUTING_AGENT.template.md should contain "Title Case"
    And CONTRIBUTING_AGENT.template.md should contain "--no-agent-provenance"
    And CONTRIBUTING_AGENT.template.md should contain "Complete provenance is platform + model + name"
    And project/issues/ and project/events/ should contain AGENTS.md with the warning
    And project/issues/ and project/events/ should contain DO_NOT_EDIT with the warning

  Scenario: Initialize with a project-local directory
    Given an empty git repository
    When I run "kanbus init --local"
    Then a "project" directory should exist
    And a "project/issues" directory should exist and contain only guard files
    And a "project-local/issues" directory should exist
    And .gitignore should include "project-local/"
    And a "CONTRIBUTING_AGENT.template.md" file should be created
    And CONTRIBUTING_AGENT.template.md should contain "This is The Way."
    And CONTRIBUTING_AGENT.template.md should contain "Agent provenance metadata"
    And CONTRIBUTING_AGENT.template.md should contain "Title Case"
    And CONTRIBUTING_AGENT.template.md should contain "--no-agent-provenance"
    And CONTRIBUTING_AGENT.template.md should contain "Complete provenance is platform + model + name"

  Scenario: Refuse to initialize when project already exists
    Given a git repository with an existing Kanbus project
    When I run "kanbus init"
    Then the command should fail with exit code 1
    And stderr should contain "already initialized"

  Scenario: Template recommends only valid CLI flags
    Given an empty git repository
    When I run "kanbus init"
    Then a "CONTRIBUTING_AGENT.template.md" file should be created
    And CONTRIBUTING_AGENT.template.md should not contain "--long"
    And CONTRIBUTING_AGENT.template.md should contain "--full-ids"


  Scenario: Initialize writes the complete default configuration
    Given an empty git repository
    When I run "kanbus init"
    Then the file ".kanbus.yml" should contain "project_management_template: null"
    And the file ".kanbus.yml" should contain "mqtt_api_token: null"
    And the file ".kanbus.yml" should contain "github_security: null"
    And the file ".kanbus.yml" should contain "ignore_paths: []"

  Scenario: Template carries the current doctrine and multi-line command examples
    Given an empty git repository
    When I run "kanbus init"
    Then a "CONTRIBUTING_AGENT.template.md" file should be created
    And CONTRIBUTING_AGENT.template.md should contain "record a running log in Kanbus comments"
    And CONTRIBUTING_AGENT.template.md should contain "Initiatives are top-level milestones"
    And CONTRIBUTING_AGENT.template.md should contain "do not need their own project-management issues"
    And CONTRIBUTING_AGENT.template.md should contain "Do not put sub-tasks under stories"
    And CONTRIBUTING_AGENT.template.md should not contain "codex   --agent-model"

  Scenario: Refuse to initialize outside a git repository
    Given a directory that is not a git repository
    When I run "kanbus init"
    Then the command should fail with exit code 1
    And stderr should contain "not a git repository"

  Scenario: Refuse to initialize inside the git metadata directory
    Given a git repository metadata directory
    When I run "kanbus init"
    Then the command should fail with exit code 1
    And stderr should contain "not a git repository"
