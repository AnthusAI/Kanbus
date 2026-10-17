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

  Scenario: A project bundle adds its own methodology
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/crap" named "crap" with heading "CRAP Reduction"
    And the Kanbus configuration selects methodologies "bdd, path:methodologies/crap"
    When I run "kanbus setup agents --force"
    Then CONTRIBUTING_AGENT.md should contain "## CRAP Reduction"
    And CONTRIBUTING_AGENT.md should contain "Project key: kbs."
    And CONTRIBUTING_AGENT.md should show "## The Cognitive Framework" before "## CRAP Reduction"

  Scenario: A project bundle replaces a built-in methodology
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/house-bdd" named "bdd" with heading "House Behavior Rules"
    And the Kanbus configuration selects methodologies "path:methodologies/house-bdd, git-flow"
    When I run "kanbus setup agents --force"
    Then CONTRIBUTING_AGENT.md should contain "## House Behavior Rules"
    And CONTRIBUTING_AGENT.md should not contain "## The Rite of Gherkin"
    And CONTRIBUTING_AGENT.md should contain "## Git Flow"

  Scenario: A project bundle and a built-in with the same name conflict
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/house-bdd" named "bdd" with heading "House Behavior Rules"
    And the Kanbus configuration selects methodologies "bdd, path:methodologies/house-bdd"
    When I run "kanbus setup agents --force"
    Then the command should fail
    And stderr should contain "methodology listed more than once: bdd"

  Scenario: A missing bundle directory fails clearly
    Given a Kanbus repository without AGENTS.md
    And the Kanbus configuration selects methodologies "path:methodologies/absent"
    When I run "kanbus setup agents --force"
    Then the command should fail
    And stderr should contain "methodology bundle not found: methodologies/absent"

  Scenario: A bundle without frontmatter fails clearly
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/plain" without frontmatter
    And the Kanbus configuration selects methodologies "path:methodologies/plain"
    When I run "kanbus setup agents --force"
    Then the command should fail
    And stderr should contain "methodology bundle methodologies/plain must begin with YAML frontmatter"

  Scenario: A methodology tool is listed in the agents file with its command
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/crap" named "crap" with a tool "report" that prints "crap report ran"
    And the Kanbus configuration selects methodologies "path:methodologies/crap"
    When I run "kanbus setup agents --force"
    Then CONTRIBUTING_AGENT.md should contain "kbs methodology run crap report"
    And CONTRIBUTING_AGENT.md should contain "Report the demo output"

  Scenario: A declared methodology tool runs from the repository through kanbus
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/crap" named "crap" with a tool "report" that prints "crap report ran"
    And the Kanbus configuration selects methodologies "path:methodologies/crap"
    When I run "kanbus methodology run crap report alpha beta"
    Then the command should succeed
    And stdout should contain "crap report ran alpha beta"

  Scenario: A failing methodology tool fails the command and reports its output
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/crap" named "crap" with a failing tool "report"
    And the Kanbus configuration selects methodologies "path:methodologies/crap"
    When I run "kanbus methodology run crap report"
    Then the command should fail
    And stderr should contain "tool failed loudly"
    And stderr should contain "exited with status 3"

  Scenario: An undeclared methodology tool fails clearly
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/crap" named "crap" with a tool "report" that prints "crap report ran"
    And the Kanbus configuration selects methodologies "path:methodologies/crap"
    When I run "kanbus methodology run crap absent"
    Then the command should fail
    And stderr should contain "methodology crap has no tool named absent (declared tools: report)"

  Scenario: A methodology that is not configured cannot run tools
    Given a Kanbus repository without AGENTS.md
    And the Kanbus configuration selects methodologies "git-flow"
    When I run "kanbus methodology run crap report"
    Then the command should fail
    And stderr should contain "methodology not configured: crap (configured methodologies: git-flow)"

  Scenario: A built-in methodology declares no tools
    Given a Kanbus repository without AGENTS.md
    When I run "kanbus methodology run bdd report"
    Then the command should fail
    And stderr should contain "methodology bdd has no tool named report (it declares no tools)"

  Scenario: A tool command outside the bundle is rejected
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/escape" declaring a tool "sneak" with command "../outside"
    And the Kanbus configuration selects methodologies "path:methodologies/escape"
    When I run "kanbus setup agents --force"
    Then the command should fail
    And stderr should contain "command must be a path inside the bundle: ../outside"

  Scenario: A tool declared twice in one bundle is rejected
    Given a Kanbus repository without AGENTS.md
    And the repository has a methodology bundle at "methodologies/twice" declaring the tool "report" twice
    And the Kanbus configuration selects methodologies "path:methodologies/twice"
    When I run "kanbus setup agents --force"
    Then the command should fail
    And stderr should contain "declares tool report more than once"

