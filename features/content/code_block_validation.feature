Feature: Code block syntax validation
  As a Kanbus user
  I want code blocks in descriptions and comments validated
  So that syntax errors are caught before content is saved

  # --- JSON validation ---

  Scenario: Create with valid JSON code block succeeds
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      Here is some config:
      ```json
      {"key": "value", "count": 42}
      ```
      """
    Then the command should succeed

  Scenario: Create with invalid JSON code block fails
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      Bad config:
      ```json
      {invalid json
      ```
      """
    Then the command should fail with exit code 1
    And stderr should contain "invalid json"
    And stderr should contain "code block"

  Scenario: Create with invalid JSON bypassed by --no-validate
    Given a Kanbus project with default configuration
    When I create an issue with --no-validate and description containing:
      """
      ```json
      {bad
      ```
      """
    Then the command should succeed

  # --- YAML validation ---

  Scenario: Create with valid YAML code block succeeds
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      Config:
      ```yaml
      key: value
      list:
        - one
        - two
      ```
      """
    Then the command should succeed

  Scenario: Create with invalid YAML code block fails
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      ```yaml
      key: value
        bad: indentation
      ```
      """
    Then the command should fail with exit code 1
    And stderr should contain "invalid yaml"
    And stderr should contain "code block"

  # --- Gherkin validation ---

  Scenario: Create with valid Gherkin code block succeeds
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      Acceptance criteria:
      ```gherkin
      Feature: Login
        Scenario: Valid credentials
          Given a registered user
          When they log in
          Then they see the dashboard
      ```
      """
    Then the command should succeed

  Scenario: Create with invalid Gherkin code block fails
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      ```gherkin
      This is not valid gherkin at all
      ```
      """
    Then the command should fail with exit code 1
    And stderr should contain "invalid gherkin"
    And stderr should contain "code block"

  # --- External tools: skip when not available ---

  Scenario: Mermaid validation skipped when mmdc not available
    Given a Kanbus project with default configuration
    And external validator "mmdc" is not available
    When I create an issue with description containing:
      """
      ```mermaid
      this is not valid mermaid
      ```
      """
    Then the command should succeed

  Scenario: PlantUML validation skipped when plantuml not available
    Given a Kanbus project with default configuration
    And external validator "plantuml" is not available
    When I create an issue with description containing:
      """
      ```plantuml
      this is not valid plantuml
      ```
      """
    Then the command should succeed

  Scenario: D2 validation skipped when d2 not available
    Given a Kanbus project with default configuration
    And external validator "d2" is not available
    When I create an issue with description containing:
      """
      ```d2
      this is not valid d2
      ```
      """
    Then the command should succeed

  # --- Comment validation ---

  Scenario: Comment with invalid JSON code block fails
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And the current user is "dev@example.com"
    When I comment on "kanbus-aaa" with text containing:
      """
      ```json
      {bad json
      ```
      """
    Then the command should fail with exit code 1
    And stderr should contain "invalid json"
    And stderr should contain "code block"

  Scenario: Comment with --no-validate bypasses validation
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    And the current user is "dev@example.com"
    When I comment on "kanbus-aaa" with --no-validate and text containing:
      """
      ```json
      {bad json
      ```
      """
    Then the command should succeed

  # --- Update validation ---

  Scenario: Update description with invalid YAML code block fails
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with title "Old Title"
    When I update "kanbus-aaa" with description containing:
      """
      ```yaml
      key: value
        bad: indentation
      ```
      """
    Then the command should fail with exit code 1
    And stderr should contain "invalid yaml"
    And stderr should contain "code block"

  # --- Edge cases ---

  Scenario: Unknown language identifiers are not validated
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      ```python
      def broken(: pass
      ```
      """
    Then the command should succeed

  Scenario: Code blocks without language identifier are not validated
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      ```
      just some text {{{
      ```
      """
    Then the command should succeed

  Scenario: Multiple code blocks validated independently
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      Valid JSON:
      ```json
      {"ok": true}
      ```

      Invalid YAML:
      ```yaml
      key: value
        bad: indentation
      ```
      """
    Then the command should fail with exit code 1
    And stderr should contain "invalid yaml"

  Scenario: Plain text without code blocks passes validation
    Given a Kanbus project with default configuration
    When I create an issue with description containing:
      """
      This is just plain text with no code blocks.
      It should pass validation without any issues.
      """
    Then the command should succeed
