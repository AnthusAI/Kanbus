Feature: Right now credential loading
  As a Kanbus user
  I want OpenAI credentials loaded from repository and congregation env files
  So that kbs now can generate summaries without exporting keys in the shell

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"
    And right now generation requires loaded OpenAI credentials

  Scenario: Right now loads OpenAI credentials from project .env
    Given OPENAI_API_KEY is provided via project .env file only
    And an issue "kanbus-rn-dotenv" exists with title "Dotenv credential issue"
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should contain "Mock right-now summary for kanbus-rn-dotenv."
    And issue "kanbus-rn-dotenv" should have a mock right now summary

  Scenario: Right now loads OpenAI credentials from congregation file
    Given OPENAI_API_KEY is provided via congregation file only
    And an issue "kanbus-rn-congregation" exists with title "Congregation credential issue"
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should contain "Mock right-now summary for kanbus-rn-congregation."
    And issue "kanbus-rn-congregation" should have a mock right now summary

  Scenario: Process environment overrides congregation and project env files
    Given OPENAI_API_KEY is provided via congregation file only
    And OPENAI_API_KEY is provided via project .env file only
    And the environment variable "OPENAI_API_KEY" is set to "from-process-env"
    And an issue "kanbus-rn-precedence" exists with title "Precedence issue"
    When I generate the right now summary for issue "kanbus-rn-precedence"
    Then the command should succeed
    And the generated right now summary should equal "Mock right-now summary for kanbus-rn-precedence."
