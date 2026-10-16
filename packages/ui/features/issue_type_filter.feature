Feature: Shared configured issue type filter
  Console and embedded boards use the same type selector and clearing behavior.

  Scenario Outline: Configured types remain available on wide and narrow screens
    Given a configured type filter at width <width> in "<mode>" mode
    Then the type choices are "All, Story, Article, Reference, Task, Initiative, Epic, Sub task"
    When I choose the issue type "Story"
    Then only filter records of type "story" are displayed
    When I choose the issue type "Article"
    Then only filter records of type "article" are displayed
    When I choose the issue type "Reference"
    Then only filter records of type "reference" are displayed
    When I choose the issue type "Reference"
    Then all filter records are displayed
    When I choose the issue type "Task"
    Then only filter records of type "task" are displayed
    When I choose the issue type "All"
    Then all filter records are displayed
    And the filter has not overflowed the host viewport

    Examples:
      | width | mode  |
      | 1440  | light |
      | 375   | dark  |

  Scenario: The shared type selector supports keyboard selection and reduced motion
    Given a configured type filter at width 375 in "light" mode
    When I select issue type "Article" with the keyboard and reduced motion
    Then only filter records of type "article" are displayed
    And the type selector has an accessible selected choice
