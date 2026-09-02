Feature: Right now summary regeneration on mutation
  As a Kanbus maintainer
  I want right-now summaries regenerated when issues change
  So that board summaries stay current without manual refresh

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Creating an issue generates a right now summary
    When I run "kanbus create Regeneration create test"
    And I capture the issue identifier
    Then the command should succeed
    And the created issue should have a mock right now summary

  Scenario: Updating an issue field refreshes its right now summary
    Given an issue "kanbus-regen01" exists with title "Update target"
    And issue "kanbus-regen01" has right now summary "Prior summary text."
    And issue "kanbus-regen01" right now state is recorded
    When I run "kanbus update kanbus-regen01 --description \"Changed description\""
    Then the command should succeed
    And issue "kanbus-regen01" should have a mock right now summary
    And issue "kanbus-regen01" right now summary should be refreshed

  Scenario: Adding a comment refreshes the issue right now summary
    Given an issue "kanbus-regen02" exists with title "Comment target"
    And issue "kanbus-regen02" has right now summary "Prior summary text."
    And issue "kanbus-regen02" right now state is recorded
    When I add a comment to issue "kanbus-regen02" with text "New activity note"
    Then the command should succeed
    And issue "kanbus-regen02" should have a mock right now summary
    And issue "kanbus-regen02" right now summary should be refreshed

  Scenario: Changing status refreshes the issue right now summary
    Given an issue "kanbus-regen03" exists with title "Status target"
    And issue "kanbus-regen03" has right now summary "Prior summary text."
    And issue "kanbus-regen03" right now state is recorded
    When I update issue "kanbus-regen03" to status "in_progress"
    Then the command should succeed
    And issue "kanbus-regen03" should have a mock right now summary
    And issue "kanbus-regen03" right now summary should be refreshed

  Scenario: Adding a dependency refreshes the issue right now summary
    Given an issue "kanbus-regen-dep-src" exists with title "Dependency source"
    And an issue "kanbus-regen-dep-tgt" exists with title "Dependency target"
    And issue "kanbus-regen-dep-src" has right now summary "Prior summary text."
    And issue "kanbus-regen-dep-src" right now state is recorded
    When I run "kanbus dep kanbus-regen-dep-src blocked-by kanbus-regen-dep-tgt"
    Then the command should succeed
    And issue "kanbus-regen-dep-src" should have a mock right now summary
    And issue "kanbus-regen-dep-src" right now summary should be refreshed

  Scenario: Deleting an issue refreshes its parent right now summary
    Given an issue "kanbus-regen-parent" of type "epic" with status "open" and title "Parent epic"
    And an issue "kanbus-regen-child" of type "task" with status "open" and parent "kanbus-regen-parent"
    And issue "kanbus-regen-parent" has right now summary "Prior parent summary."
    And issue "kanbus-regen-parent" right now state is recorded
    When I run "kanbus delete kanbus-regen-child --yes"
    Then the command should succeed
    And issue "kanbus-regen-parent" should have a mock right now summary
    And issue "kanbus-regen-parent" right now summary should be refreshed

  Scenario: Ancestor propagation refreshes parent and grandparent summaries
    Given an issue "kanbus-regen-init" of type "initiative" with status "open"
    And an issue "kanbus-regen-epic" of type "epic" with status "open" and parent "kanbus-regen-init"
    And an issue "kanbus-regen-task" of type "task" with status "open" and parent "kanbus-regen-epic"
    And issue "kanbus-regen-epic" has right now summary "Prior epic summary."
    And issue "kanbus-regen-init" has right now summary "Prior initiative summary."
    And issue "kanbus-regen-epic" right now state is recorded
    And issue "kanbus-regen-init" right now state is recorded
    When I update issue "kanbus-regen-task" to status "in_progress"
    Then the command should succeed
    And issue "kanbus-regen-task" should have a mock right now summary
    And issue "kanbus-regen-epic" should have a mock right now summary
    And issue "kanbus-regen-epic" right now summary should be refreshed
    And issue "kanbus-regen-init" should have a mock right now summary
    And issue "kanbus-regen-init" right now summary should be refreshed

  Scenario: Offline mutation preserves prior right now summary when AI is unconfigured
    Given an issue "kanbus-offline01" exists with title "Offline target"
    And issue "kanbus-offline01" has right now summary "Preserved summary."
    And the Kanbus project has no AI configuration
    When I update issue "kanbus-offline01" to status "in_progress"
    Then the command should succeed
    And issue "kanbus-offline01" should have right now summary "Preserved summary."

  Scenario: Disabled right now configuration skips summary generation on mutation
    Given right now summary generation is disabled
    And an issue "kanbus-disabled01" exists with title "Disabled target"
    When I update issue "kanbus-disabled01" to status "in_progress"
    Then the command should succeed
    And issue "kanbus-disabled01" should have no right now summary
