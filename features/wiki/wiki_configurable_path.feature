Feature: Configurable wiki path
  As a Kanbus user
  I want to configure where wiki pages live
  So that I can use docs/, wiki/, or any custom folder instead of project/wiki

  Scenario: Default wiki path when wiki_directory is absent
    Given a Kanbus project with default configuration
    And a wiki page "default.md" with content "Default path"
    When I run "kanbus wiki render project/wiki/default.md"
    Then the command should succeed
    And stdout should contain "Default path"
    And the wiki root should be "project/wiki"

  Scenario: Custom wiki_directory uses docs folder
    Given a Kanbus project with wiki_directory set to "docs"
    And a wiki page "page.md" with content:
      """
      # Page
      Content in docs.
      """
    When I run "kanbus wiki render project/docs/page.md"
    Then the command should succeed
    And stdout should contain "Content in docs"
    And the wiki root should be "project/docs"

  Scenario: Wiki at repo root via relative path
    Given a Kanbus project with wiki_directory set to "../wiki"
    And a wiki page "root.md" with content "Wiki at repo root"
    When I run "kanbus wiki render wiki/root.md"
    Then the command should succeed
    And stdout should contain "Wiki at repo root"
    And the wiki root should be "wiki"

  Scenario: CLI render respects wiki_directory
    Given a Kanbus project with wiki_directory set to "docs"
    And a wiki page "arch.md" with content:
      """
      Open: {{ count(status="open") }}
      """
    And open tasks "One" and "Two" exist
    When I run "kanbus wiki render project/docs/arch.md"
    Then the command should succeed
    And stdout should contain "Open: 2"

  Scenario: List pages uses wiki_directory
    Given a Kanbus project with wiki_directory set to "docs"
    And a wiki page "a.md" with content "A"
    And a wiki page "b.md" with content "B"
    When I run "kanbus wiki list"
    Then the command should succeed
    And stdout should contain "project/docs/a.md"
    And stdout should contain "project/docs/b.md"

  Scenario: Invalid wiki_directory path fails configuration
    Given a Kanbus project with default configuration
    And the Kanbus configuration has wiki_directory set to "../../etc"
    When I load the configuration
    Then the command should fail with exit code 1
    And stderr should contain "wiki_directory"
