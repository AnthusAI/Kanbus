Feature: Right now summary generation
  As a Kanbus maintainer
  I want to generate terse right-now summaries for issues
  So that agents and humans can scan board status quickly

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Generating a right-now summary for an active issue produces a one-sentence string
    Given an issue "kanbus-rn1" exists with title "Implement OAuth2 flow"
    When I generate the right now summary for issue "kanbus-rn1"
    Then the command should succeed
    And the generated right now summary should be non-empty
    And the generated right now summary should equal "Mock right-now summary for kanbus-rn1."

  Scenario: The summary respects max_length
    Given the right now max length is set to 80
    And an issue "kanbus-rn2" exists with title "Short issue"
    When I generate the right now summary for issue "kanbus-rn2"
    Then the command should succeed
    And the generated right now summary length should be at most 80

  Scenario: The summary does not restate status keywords
    Given an issue "kanbus-rn3" exists with title "Review pull request"
    And issue "kanbus-rn3" has status "in_progress"
    When I generate the right now summary for issue "kanbus-rn3"
    Then the command should succeed
    And the generated right now summary should not contain status keywords

  Scenario: Mock AI is used without calling LiteLLM
    Given an issue "kanbus-rn4" exists with title "Test issue"
    When I generate the right now summary for issue "kanbus-rn4"
    Then the command should succeed
    And the LLM usage log should contain a right_now_summary entry
    And the LiteLLM API should not be called

  Scenario: A second generation for the same unchanged issue does not error
    Given an issue "kanbus-rn5" exists with title "Stable issue"
    When I generate the right now summary for issue "kanbus-rn5"
    And I generate the right now summary for issue "kanbus-rn5"
    Then the command should succeed

  Scenario: Generation fails when AI provider is not configured
    Given the Kanbus project has no AI configuration
    And an issue "kanbus-rn6" exists with title "No AI issue"
    When I generate the right now summary for issue "kanbus-rn6"
    Then right now summary generation should fail with "Right-now summary generation requires ai.provider litellm in .kanbus.yml"
