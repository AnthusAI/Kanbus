Feature: Methodologies assembled into CONTRIBUTING_AGENT.md
  As a team adopting Kanbus
  I want the process opinions in CONTRIBUTING_AGENT.md to come from methodologies I select
  So that Kanbus core carries no process opinions of its own

  Scenario: Default methodologies when none are configured
    Given a Kanbus repository without AGENTS.md
    When I run "kanbus setup agents --force"
    Then CONTRIBUTING_AGENT.md should exist
    And CONTRIBUTING_AGENT.md should contain "## The Rite of Gherkin"
    And CONTRIBUTING_AGENT.md should contain "## Git Flow"
    And CONTRIBUTING_AGENT.md should contain "## Semantic Release Alignment"

  Scenario: An empty methodology list yields core guidance only
    Given a Kanbus repository without AGENTS.md
    And the Kanbus configuration selects no methodologies
    When I run "kanbus setup agents --force"
    Then CONTRIBUTING_AGENT.md should exist
    And CONTRIBUTING_AGENT.md should contain "## The Order of Being"
    And CONTRIBUTING_AGENT.md should not contain "Gherkin"
    And CONTRIBUTING_AGENT.md should not contain "## Git Flow"

  Scenario: Selected methodologies render in configured order
    Given a Kanbus repository without AGENTS.md
    And the Kanbus configuration selects methodologies "git-flow, bdd"
    When I run "kanbus setup agents --force"
    Then CONTRIBUTING_AGENT.md should show "## Git Flow" before "## The Cognitive Framework"

  Scenario: A single methodology excludes the others
    Given a Kanbus repository without AGENTS.md
    And the Kanbus configuration selects methodologies "git-flow"
    When I run "kanbus setup agents --force"
    Then CONTRIBUTING_AGENT.md should contain "## Git Flow"
    And CONTRIBUTING_AGENT.md should not contain "Gherkin"

  Scenario: Unknown methodology names fail clearly
    Given a Kanbus repository without AGENTS.md
    And the Kanbus configuration selects methodologies "scrum-of-scrums"
    When I run "kanbus setup agents --force"
    Then the command should fail
    And stderr should contain "unknown methodology: scrum-of-scrums"

  Scenario: Duplicated methodology names fail clearly
    Given a Kanbus repository without AGENTS.md
    And the Kanbus configuration selects methodologies "bdd, bdd"
    When I run "kanbus setup agents --force"
    Then the command should fail
    And stderr should contain "methodology listed more than once: bdd"
