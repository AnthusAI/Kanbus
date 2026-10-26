Feature: Issue card subtitle
  As an application developer
  I want board cards to show an issue subtitle under its title when my application supplies one
  So that readers see the title and its blurb on the board

  Scenario: A card with a subtitle shows it under the title
    Given a host application with article and task issues
    When the host renders an article board
    Then the card "article-2" shows the subtitle "Why the harbor vote slipped a week" under its title

  Scenario: A card without a subtitle renders no empty subtitle element
    Given a host application with article and task issues
    When the host renders an article board
    Then the card "article-3" has no subtitle element

  Scenario: A changed subtitle re-renders the memoized card
    Given a host application with article and task issues
    When the host renders an article board
    And the host changes the subtitle of issue "article-2" to "Council adjourns without a vote"
    Then the card "article-2" shows the subtitle "Council adjourns without a vote" under its title

  Scenario: An empty subtitle renders no subtitle element
    Given a host application with article and task issues
    When the host renders an article board
    And the host changes the subtitle of issue "article-2" to ""
    Then the card "article-2" has no subtitle element
