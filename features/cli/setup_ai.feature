Feature: Setup AI credentials
  As a Kanbus user
  I want to store my LLM API key once at the user level
  So that compaction and summaries work in every project without per-project .env files

  Scenario: Store an API key in the user-level env file
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    When I run "kanbus setup ai --key test-openai-key-value"
    Then the command should succeed
    And stdout should contain "Saved OPENAI_API_KEY to ~/.kanbus.env"
    And stdout should not contain "test-openai-key-value"
    And the congregation env file should contain "OPENAI_API_KEY=test-openai-key-value"
    And the congregation env file should have mode 600

  Scenario: Update an existing key while preserving other lines
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    And the congregation env file contains:
      """
      # my keys
      OTHER_SETTING=1
      OPENAI_API_KEY=old-key-value
      """
    When I run "kanbus setup ai --key new-key-value"
    Then the command should succeed
    And the congregation env file should contain "# my keys"
    And the congregation env file should contain "OTHER_SETTING=1"
    And the congregation env file should contain "OPENAI_API_KEY=new-key-value"
    And the congregation env file should not contain "old-key-value"

  Scenario: Store a key under a different variable name
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    When I run "kanbus setup ai --variable ANTHROPIC_API_KEY --key test-anthropic-key-value"
    Then the command should succeed
    And stdout should contain "Saved ANTHROPIC_API_KEY to ~/.kanbus.env"
    And the congregation env file should contain "ANTHROPIC_API_KEY=test-anthropic-key-value"

  Scenario: Status reports the congregation file without printing the key
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    And OPENAI_API_KEY is absent from the process environment
    And the congregation env file contains:
      """
      OPENAI_API_KEY=secret-value-123
      """
    When I run "kanbus setup ai --status"
    Then the command should succeed
    And stdout should contain "OPENAI_API_KEY: ~/.kanbus.env"
    And stdout should not contain "secret-value-123"

  Scenario: Status reports when no key is configured
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    And OPENAI_API_KEY is absent from the process environment
    When I run "kanbus setup ai --status"
    Then the command should succeed
    And stdout should contain "OPENAI_API_KEY: not set"
    And stdout should contain "setup ai"

  Scenario: Setup fails without a key when not interactive
    Given an empty git repository
    And the congregation env file is redirected to a temporary home
    When I run "kanbus setup ai" non-interactively
    Then the command should fail with exit code 1
    And stderr should contain "no key provided"

  Scenario: Doctor reports the credential source
    Given a Kanbus project with default configuration
    And the congregation env file is redirected to a temporary home
    And OPENAI_API_KEY is absent from the process environment
    When I run "kanbus doctor"
    Then the command should succeed
    And stdout should contain "ok"
    And stdout should contain "ai credentials: OPENAI_API_KEY not set"
