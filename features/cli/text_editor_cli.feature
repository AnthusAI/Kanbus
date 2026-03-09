Feature: Text editor CLI (edit subcommands)
  As an agent using the Kanbus CLI
  I want file edit commands that mirror the Anthropic text editor tool
  So that I can view, replace, create, and insert text via kbs

  Background:
    Given an empty git repository
    And I run "kanbus init"
    And the command should succeed

  Scenario: View file contents
    Given a file "edit-test.txt" with content:
      """
      line one
      line two
      line three
      """
    When I run "kanbus edit view edit-test.txt"
    Then the command should succeed
    And stdout should contain "1: line one"
    And stdout should contain "2: line two"
    And stdout should contain "3: line three"

  Scenario: View directory listing
    Given a file "dir-view/a.txt" with content "a"
    And a file "dir-view/b.txt" with content "b"
    When I run "kanbus edit view dir-view"
    Then the command should succeed
    And stdout should contain "a.txt"
    And stdout should contain "b.txt"

  Scenario: View file with line range
    Given a file "range.txt" with content:
      """
      first
      second
      third
      fourth
      """
    When I run "kanbus edit view range.txt --view-range 2 3"
    Then the command should succeed
    And stdout should contain "2: second"
    And stdout should contain "3: third"
    And stdout should not contain "first"
    And stdout should not contain "fourth"

  Scenario: Str-replace succeeds when exactly one match
    Given a file "replace-one.txt" with content "hello world"
    When I run "kanbus edit str-replace replace-one.txt --old-str hello --new-str hi"
    Then the command should succeed
    And stdout should contain "Successfully replaced text at exactly one location"
    And the file "replace-one.txt" should contain "hi world"

  Scenario: Str-replace fails when no match
    Given a file "replace-none.txt" with content "hello world"
    When I run "kanbus edit str-replace replace-none.txt --old-str xyz --new-str abc"
    Then the command should fail with exit code 1
    And stderr should contain "no match found"

  Scenario: Str-replace fails when multiple matches
    Given a file "replace-many.txt" with content "foo\nfoo\nfoo"
    When I run "kanbus edit str-replace replace-many.txt --old-str foo --new-str bar"
    Then the command should fail with exit code 1
    And stderr should contain "found 3 matches"
    And stderr should contain "unique match"

  Scenario: Create new file succeeds
    When I run "kanbus edit create newfile.txt --file-text 'content here'"
    Then the command should succeed
    And stdout should contain "Successfully created file"
    And the file "newfile.txt" should exist
    And the file "newfile.txt" should contain "content here"

  Scenario: Create fails when file already exists
    Given a file "exists.txt" with content "existing"
    When I run "kanbus edit create exists.txt --file-text 'new content'"
    Then the command should fail with exit code 1
    And stderr should contain "file already exists"

  Scenario: Insert at beginning
    Given a file "insert-start.txt" with content "original"
    When I run "kanbus edit insert insert-start.txt --insert-line 0 --insert-text prepended"
    Then the command should succeed
    And stdout should contain "Successfully inserted text"
    And the file "insert-start.txt" should contain "prepended"
    And the file "insert-start.txt" should contain "original"
    And "prepended" should appear before "original" in the file "insert-start.txt"

  Scenario: Insert after line one
    Given a file "insert-mid.txt" with content:
      """
      first
      third
      """
    When I run "kanbus edit insert insert-mid.txt --insert-line 1 --insert-text second"
    Then the command should succeed
    And the file "insert-mid.txt" should contain "second"
    And "second" should appear after "first" in the file "insert-mid.txt"
    And "second" should appear before "third" in the file "insert-mid.txt"

  Scenario: Insert fails when line exceeds file length
    Given a file "insert-short.txt" with content "one line"
    When I run "kanbus edit insert insert-short.txt --insert-line 10 --insert-text x"
    Then the command should fail with exit code 1
    And stderr should contain "insert_line exceeds file length"

  Scenario: View fails for missing file
    When I run "kanbus edit view missing.txt"
    Then the command should fail with exit code 1
    And stderr should contain "not found"
