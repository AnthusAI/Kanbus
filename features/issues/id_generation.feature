Feature: Issue ID generation
  As a Taskulus user
  I want issue IDs that are unique and predictable
  So that I can reference issues reliably

  Scenario: Generated IDs follow the prefix-hex format
    Given a project with prefix "tsk"
    When I generate an issue ID
    Then the ID should match the pattern "tsk-[0-9a-f]{6}"

  Scenario: Generated IDs are unique across multiple creations
    Given a project with prefix "tsk"
    When I generate 100 issue IDs
    Then all 100 IDs should be unique

  Scenario: ID generation handles collision with existing issues
    Given a project with an existing issue "tsk-aaaaaa"
    And the hash function would produce "aaaaaa" for the next issue
    When I generate an issue ID
    Then the ID should not be "tsk-aaaaaa"
    And the ID should match the pattern "tsk-[0-9a-f]{6}"

  Scenario: ID generation fails after repeated collisions
    Given a project with prefix "tsk"
    And the random bytes are fixed to "0000000000000000"
    And the existing issue set includes the generated ID
    When I generate an issue ID expecting failure
    Then ID generation should fail with "unable to generate unique id after 10 attempts"

  Scenario: ID generation rejects invalid test random bytes
    Given a project with prefix "tsk"
    And the random bytes are fixed to "invalid"
    When I generate an issue ID expecting failure
    Then ID generation should fail with "invalid TASKULUS_TEST_RANDOM_BYTES"

  Scenario: ID generation rejects non-hex test random bytes
    Given a project with prefix "tsk"
    And the random bytes are fixed to "zz"
    When I generate an issue ID expecting failure
    Then ID generation should fail with "invalid TASKULUS_TEST_RANDOM_BYTES"
