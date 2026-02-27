Feature: Rich text quality signals
  As a CLI user or AI coding agent
  I want the CLI to repair common text malformations and suggest improvements
  So that issue descriptions and comments are always well-formatted

  # --- Escape sequence repair ---

  Scenario: Literal \n sequences are replaced with real newlines in a description
    Given a Kanbus project with default configuration
    When I create an issue with a literal backslash-n description "Summary\nBody line one\nBody line two"
    Then the command should succeed
    And the stored description contains real newlines

  Scenario: A warning is emitted when \n replacement occurs in a description
    Given a Kanbus project with default configuration
    When I create an issue with a literal backslash-n description "Summary\nBody"
    Then stderr should contain "WARNING"
    And stderr should contain "escape sequences"
    And stderr should contain "replaced"

  Scenario: A warning is emitted when \n replacement occurs in a comment
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And the current user is "dev@example.com"
    When I comment on "kanbus-aaa" with literal backslash-n text "Line one\nLine two"
    Then the command should succeed
    And stderr should contain "WARNING"
    And stderr should contain "escape sequences"

  @skip
  Scenario: No warning is emitted for clean text with real newlines
    Given a Kanbus project with default configuration
    When I create an issue with a clean multi-line description
    Then the command should succeed
    And stderr should not contain "escape sequences"

  # --- Markdown suggestions ---

  Scenario: Suggestion emitted when description has no Markdown
    Given a Kanbus project with default configuration
    When I create an issue with a plain-text description "This is plain text with no formatting"
    Then the command should succeed
    And stderr should contain "SUGGESTION"
    And stderr should contain "Markdown"

  Scenario: Suggestion emitted when comment has no Markdown
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And the current user is "dev@example.com"
    When I comment on "kanbus-aaa" with plain text "This is a plain comment with no formatting"
    Then the command should succeed
    And stderr should contain "SUGGESTION"
    And stderr should contain "Markdown"

  Scenario: No Markdown suggestion when description contains Markdown
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      ## Overview

      This issue tracks **important work**.
      """
    Then the command should succeed
    And stderr should not contain "Markdown formatting is supported"

  Scenario: Markdown suggestion also applies on update
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Old Title"
    When I update "kanbus-aaa" with plain-text description "Updated plain text description"
    Then the command should succeed
    And stderr should contain "SUGGESTION"
    And stderr should contain "Markdown"

  # --- Diagram suggestions ---

  Scenario: Suggestion emitted when description has no diagram
    Given a Kanbus project with default configuration
    When I create an issue with a plain-text description "This is plain text with no formatting"
    Then stderr should contain "SUGGESTION"
    And stderr should contain "mermaid"

  Scenario: Suggestion emitted when comment has no diagram
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And the current user is "dev@example.com"
    When I comment on "kanbus-aaa" with plain text "This is a plain comment with no formatting"
    Then stderr should contain "mermaid"

  Scenario: No diagram suggestion when a diagram is present
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      ## Flow

      ```mermaid
      graph TD
        A --> B
      ```
      """
    Then the command should succeed
    And stderr should not contain "Diagrams can be embedded"

  # --- Follow-up command hints ---

  Scenario: Suggestion after creating an issue includes an update hint
    Given a Kanbus project with default configuration
    When I create an issue with a plain-text description "This is plain text with no formatting"
    Then stderr should contain "kbs update"
    And stderr should contain "--description"

  Scenario: Suggestion after adding a comment includes a comment update hint
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And the current user is "dev@example.com"
    When I comment on "kanbus-aaa" with plain text "This is a plain comment with no formatting"
    Then stderr should contain "kbs comment update"

  Scenario: Suggestion after updating a description includes a re-update hint
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Old Title"
    When I update "kanbus-aaa" with plain-text description "Updated plain text description"
    Then stderr should contain "kbs update"
    And stderr should contain "--description"

  # --- No signals on clean, well-formatted text ---

  Scenario: Clean Markdown description with diagram emits no suggestions
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      ## Summary

      This issue is about **improving quality**.

      ```mermaid
      graph TD
        A --> B
      ```
      """
    Then the command should succeed
    And stderr should not contain "SUGGESTION"
