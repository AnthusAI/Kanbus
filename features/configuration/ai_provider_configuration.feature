Feature: AI provider configuration
  As a Kanbus administrator
  I want to configure an AI provider and model in kanbus.yml
  So that wiki reports can use LLMs for summarization

  Scenario: Valid AI configuration
    Given a Kanbus project with a file "kanbus.yml" containing:
      """
      ai:
        provider: "openai"
        model: "gpt-4o"
      """
    When I load the configuration
    Then the command should succeed
    And the AI provider should be "openai"
