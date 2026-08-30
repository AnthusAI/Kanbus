Feature: Kanbus version gate
  As a Kanbus user
  I want the CLI to enforce the project's required kanbus-version
  So that outdated CLIs fail early with a clear upgrade message

  Scenario: List fails when the running CLI is too old
    Given a Kanbus project with default configuration
    And the project requires kanbus version "99.0.0"
    When I run "kanbus list"
    Then the command should fail with exit code 1
    And stderr should contain "Kanbus CLI"
    And stderr should contain "99.0.0"
    And stderr should contain "pip install --upgrade kanbus"
    And stderr should contain "cargo install kanbus --locked --force"

  Scenario: Doctor fails when the running CLI is too old
    Given a Kanbus project with default configuration
    And the project requires kanbus version "99.0.0"
    When I run "kanbus doctor"
    Then the command should fail with exit code 1
    And stderr should contain "Kanbus CLI"
    And stderr should contain "99.0.0"
    And stderr should contain "pip install --upgrade kanbus"
    And stderr should contain "cargo install kanbus --locked --force"
    And stdout should not contain "ok"

  Scenario: Doctor succeeds when kanbus-version is permissive
    Given a Kanbus project with default configuration
    And the project requires kanbus version "0.0.0"
    When I run "kanbus doctor"
    Then the command should succeed
    And stdout should contain "ok"

  Scenario: List succeeds when kanbus-version matches the running CLI core version
    Given a Kanbus project with default configuration
    And the project requires the running kanbus CLI core version
    When I run "kanbus list"
    Then the command should succeed

  Scenario: Missing kanbus-version file skips the version check
    Given a Kanbus project with default configuration
    When I run "kanbus doctor"
    Then the command should succeed
    And stdout should contain "ok"

  Scenario: Invalid kanbus-version contents fail before doctor reports ok
    Given a Kanbus project with default configuration
    And kanbus-version contains invalid contents
    When I run "kanbus doctor"
    Then the command should fail with exit code 1
    And stderr should contain "kanbus-version is invalid: expected a single MAJOR.MINOR.PATCH value"
    And stdout should not contain "ok"

  Scenario: Version flag is exempt from the kanbus-version check
    Given a Kanbus project with default configuration
    And the project requires kanbus version "99.0.0"
    When I run "kanbus --version"
    Then the command should succeed
