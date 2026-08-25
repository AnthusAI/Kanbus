Feature: Sync Error Handling
  In order to ensure Kanbus fails gracefully
  As a user
  I want synchronization commands to report clear errors on failures

  Scenario: Snyk sync handles connection errors gracefully
    
    Given a Kanbus project with a file "kanbus.yml" containing:
      """
      project_key: KANBUS
      snyk:
        org_id: test-org
        min_severity: low
      """
    And the environment variable "KANBUS_SNYK_API_BASE" is set to "http://127.0.0.1:9"
    And the environment variable "SNYK_TOKEN" is set to "fake_token"
    When I run "kanbus snyk pull"
    Then the command should fail with exit code 1
    And stderr should contain "request failed"

  Scenario: Snyk sync requires issues directory
    
    Given a Kanbus project with a file "kanbus.yml" containing:
      """
      project_key: KANBUS
      snyk:
        org_id: test-org
        min_severity: low
      """
    And the environment variable "SNYK_TOKEN" is set to "fake_token"
    And the issues directory is missing
    When I run "kanbus snyk pull"
    Then the command should fail with exit code 1
    And stderr should contain "issues directory does not exist"

  Scenario: GitHub security sync handles connection errors gracefully
    
    Given a Kanbus project with a file "kanbus.yml" containing:
      """
      project_key: KANBUS
      github_security:
        repo: test/test
        dependabot:
          state: open
          min_severity: low
      """
    And the environment variable "KANBUS_GITHUB_API_BASE" is set to "http://127.0.0.1:9"
    And the environment variable "GITHUB_TOKEN" is set to "fake_token"
    When I run "kanbus github dependabot pull"
    Then the command should fail with exit code 1
    And stderr should contain "request failed"

  Scenario: GitHub security sync handles invalid dependabot state
    
    Given a Kanbus project with a file "kanbus.yml" containing:
      """
      project_key: KANBUS
      github_security:
        repo: test/test
        dependabot:
          state: invalid_state
          min_severity: low
      """
    And the environment variable "GITHUB_TOKEN" is set to "fake_token"
    When I run "kanbus github dependabot pull"
    Then the command should fail with exit code 1
    And stderr should contain "invalid dependabot state"
