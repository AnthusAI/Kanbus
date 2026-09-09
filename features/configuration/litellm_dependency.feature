Feature: LiteLLM dependency for AI commands
  As a Kanbus user
  I want litellm installed with the kanbus package
  So that kbs now and kbs standup work after uv tool install

  Scenario: Missing litellm reports a curated error without traceback
    Given a Kanbus project with default configuration
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"
    And litellm is not installed
    And an issue "kanbus-litellm-missing" exists with title "Missing dependency test"
    And issue "kanbus-litellm-missing" has status "in_progress"
    When I run "kanbus now"
    Then the command should fail with exit code 1
    And stderr should contain "litellm is required for right-now summary generation"
    And stderr should not contain "Traceback"
