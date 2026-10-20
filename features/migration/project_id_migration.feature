Feature: Project id migration
  Existing projects gain a project_id through an explicit migration command.

  Scenario: Migration writes a project_id when it is absent
    Given a Kanbus project with a minimal configuration file
    When I run "kanbus migrate project-id"
    Then the command should succeed
    And stdout should contain "project_id written:"
    And the file ".kanbus.yml" should contain "project_id:"
    And the file ".kanbus.yml" should contain "project_key: tsk"

  Scenario: Migration leaves an existing project_id untouched
    Given a Kanbus project with a minimal configuration file
    When I run "kanbus migrate project-id"
    And I run "kanbus migrate project-id"
    Then the command should succeed
    And stdout should contain "project_id already set:"
