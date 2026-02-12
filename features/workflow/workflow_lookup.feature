Feature: Workflow lookup
  As a Taskulus maintainer
  I want workflow lookup to fail when defaults are missing
  So that configuration errors surface early

  Scenario: Missing default workflow raises an error
    Given a configuration without a default workflow
    When I look up the workflow for issue type "task"
    Then workflow lookup should fail with "default workflow not defined"
