Feature: Right now summary roll-up and context assembly
  As a Kanbus maintainer
  I want parent right-now context assembled from direct children
  So that hierarchical summaries roll up without waiting for compaction

  Background:
    Given a Kanbus project with default configuration

  Scenario: Leaf issue context has title description and recent activity without child summaries
    Given an issue "kanbus-leaf01" exists with title "Leaf task"
    And issue "kanbus-leaf01" description is "Do the leaf work"
    And a comment on issue "kanbus-leaf01" contains "Started implementation"
    When I build the right now context for issue "kanbus-leaf01"
    Then the right now context title should be "Leaf task"
    And the right now context description should be "Do the leaf work"
    And the right now context recent activity should contain "Started implementation"
    And the right now context should have no child summaries

  Scenario: Parent issue context includes one child summary per direct child
    Given an issue "kanbus-epic01" of type "epic" with status "open" and title "Parent epic"
    And an issue "kanbus-task01" of type "task" with status "open" and parent "kanbus-epic01"
    And an issue "kanbus-task02" of type "task" with status "open" and parent "kanbus-epic01"
    And issue "kanbus-task01" has right now summary "Task one is moving."
    And issue "kanbus-task02" has right now summary "Task two is blocked."
    When I build the right now context for issue "kanbus-epic01"
    Then the right now context should have 2 child summaries
    And the child summary for "kanbus-task01" should be "Task one is moving."
    And the child summary for "kanbus-task02" should be "Task two is blocked."

  Scenario: Child summary uses right_now_summary when set
    Given an issue "kanbus-epic02" of type "epic" with status "open"
    And an issue "kanbus-task03" of type "task" with status "open" and parent "kanbus-epic02"
    And issue "kanbus-task03" has right now summary "Child summary from cache."
    When I build the right now context for issue "kanbus-epic02"
    Then the child summary for "kanbus-task03" should be "Child summary from cache."

  Scenario: Child summary falls back to bounded raw rendering when right_now_summary is absent
    Given an issue "kanbus-epic03" of type "epic" with status "open"
    And an issue "kanbus-task04" of type "task" with status "open" and parent "kanbus-epic03" and title "Raw child"
    And issue "kanbus-task04" description is "Child description text"
    When I build the right now context for issue "kanbus-epic03"
    Then the child summary for "kanbus-task04" should contain "Raw child"
    And the child summary for "kanbus-task04" should contain "Child description text"

  Scenario: Child raw rendering is bounded by the character budget
    Given an issue "kanbus-epic04" of type "epic" with status "open"
    And an issue "kanbus-task05" of type "task" with status "open" and parent "kanbus-epic04"
    And issue "kanbus-task05" has description with 2500 characters
    When I build the right now context for issue "kanbus-epic04"
    Then the child summary for "kanbus-task05" length should be at most 2000

  Scenario: Parent context only rolls up direct children per hierarchy
    Given an issue "kanbus-init01" of type "initiative" with status "open"
    And an issue "kanbus-epic05" of type "epic" with status "open" and parent "kanbus-init01"
    And an issue "kanbus-task06" of type "task" with status "open" and parent "kanbus-epic05"
    And issue "kanbus-epic05" has right now summary "Epic summary."
    And issue "kanbus-task06" has right now summary "Task summary."
    When I build the right now context for issue "kanbus-init01"
    Then the right now context should have 1 child summary
    And the child summary for "kanbus-epic05" should be "Epic summary."
    And the right now context should not have child summary for "kanbus-task06"

  @wip
  Scenario: Parent right-now summary is regenerated when a child summary changes
    Given an issue "kanbus-epic10" of type "epic" with status "open"
    And an issue "kanbus-task10" of type "task" with status "open" and parent "kanbus-epic10"
    And issue "kanbus-epic10" has right now summary "Parent reflects old child state."
    And issue "kanbus-task10" has right now summary "Child was stable."
    When issue "kanbus-task10" has right now summary "Child has changed."
    And the parent right now summary is regenerated for issue "kanbus-epic10"
    Then issue "kanbus-epic10" should have a right now summary that reflects the child change

  @wip
  Scenario: Parent invalidation propagates up the hierarchy when a descendant changes
    Given an issue "kanbus-init10" of type "initiative" with status "open"
    And an issue "kanbus-epic11" of type "epic" with status "open" and parent "kanbus-init10"
    And an issue "kanbus-task11" of type "task" with status "open" and parent "kanbus-epic11"
    And issue "kanbus-init10" has right now summary "Initiative summary."
    And issue "kanbus-epic11" has right now summary "Epic summary."
    And issue "kanbus-task11" has right now summary "Task summary."
    When issue "kanbus-task11" has right now summary "Task changed."
    Then issue "kanbus-epic11" right now summary should be invalidated
    And issue "kanbus-init10" right now summary should be invalidated
