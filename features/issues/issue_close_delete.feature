Feature: Issue close and delete

  Scenario: Close an issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with status "open"
    When I run "kanbus close kanbus-aaa"
    Then the command should succeed
    And stdout should contain "Closed kanbus-aaa"
    And issue "kanbus-aaa" should have status "closed"
    And issue "kanbus-aaa" should have a closed_at timestamp

  Scenario: Close an issue with a comment
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with status "open"
    And the current user is "dev@example.com"
    When I run "kanbus close kanbus-aaa --comment 'Completed and verified.'"
    Then the command should succeed
    And stdout should contain "Closed kanbus-aaa"
    And issue "kanbus-aaa" should have status "closed"
    And issue "kanbus-aaa" should have a closed_at timestamp
    And issue "kanbus-aaa" should have 1 comments
    And issue "kanbus-aaa" should have comment text "Completed and verified."

  Scenario: Close with a whitespace comment fails without mutation
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists with status "open"
    When I run "kanbus close kanbus-aaa --comment '   '"
    Then the command should fail with exit code 1
    And stderr should contain "comment text is required"
    And issue "kanbus-aaa" should have status "open"
    And issue "kanbus-aaa" should have 0 comments

  Scenario: Close failure after a comment keeps the comment
    Given a Kanbus project with default configuration
    And the Kanbus hooks configuration is:
      """
      enabled: true
      default_timeout_ms: 5000
      before:
        issue.close:
          - id: reject-close
            command: ["sh", "-c", "exit 7"]
      """
    And an issue "kanbus-aaa" exists with status "open"
    When I run "kanbus close kanbus-aaa --comment 'Attempted close note'"
    Then the command should fail with exit code 1
    And stderr should contain "reject-close"
    And issue "kanbus-aaa" should have status "open"
    And issue "kanbus-aaa" should have 1 comments
    And issue "kanbus-aaa" should have comment text "Attempted close note"

  Scenario: Close missing issue fails
    Given a Kanbus project with default configuration
    When I run "kanbus close kanbus-missing"
    Then the command should fail with exit code 1
    And stderr should contain "not found"

  Scenario: Delete an issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    When I run "kanbus delete kanbus-aaa --yes"
    Then the command should succeed
    And stdout should contain "Deleted kanbus-aaa"
    And issue "kanbus-aaa" should not exist

  Scenario: Delete without --yes when user declines leaves issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    When I run "kanbus delete kanbus-aaa" and respond "n"
    Then the command should succeed
    And issue "kanbus-aaa" should exist

  Scenario: Delete without --yes in non-interactive mode fails
    Given a Kanbus project with default configuration
    And an issue "kanbus-aaa" exists
    When I run "kanbus delete kanbus-aaa" non-interactively
    Then the command should fail with exit code 1
    And stderr should contain "re-run with --yes"

  Scenario: Delete with --recursive --yes removes issue and descendants
    Given a Kanbus project with default configuration
    And an issue "kanbus-parent" exists
    And an issue "kanbus-child" exists with parent "kanbus-parent"
    When I run "kanbus delete kanbus-parent --recursive --yes"
    Then the command should succeed
    And issue "kanbus-parent" should not exist
    And issue "kanbus-child" should not exist

  Scenario: Delete with --recursive when user confirms both removes all
    Given a Kanbus project with default configuration
    And an issue "kanbus-parent" exists
    And an issue "kanbus-child" exists with parent "kanbus-parent"
    When I run "kanbus delete kanbus-parent --recursive" with stdin "y\ny"
    Then the command should succeed
    And issue "kanbus-parent" should not exist
    And issue "kanbus-child" should not exist

  Scenario: Delete with --recursive when user declines second prompt deletes only target
    Given a Kanbus project with default configuration
    And an issue "kanbus-parent" exists
    And an issue "kanbus-child" exists with parent "kanbus-parent"
    When I run "kanbus delete kanbus-parent --recursive" with stdin "y\nn"
    Then the command should succeed
    And issue "kanbus-parent" should not exist
    And issue "kanbus-child" should exist

  Scenario: Delete missing issue fails
    Given a Kanbus project with default configuration
    When I run "kanbus delete kanbus-missing --yes"
    Then the command should fail with exit code 1
    And stderr should contain "not found"
