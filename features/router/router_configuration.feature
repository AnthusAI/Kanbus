Feature: Optional Issue Router configuration
  As a Kanbus maintainer
  I want the Issue Router to be optional and strictly configured
  So that projects without router settings keep their normal Kanbus behavior

  Scenario: Router commands require an explicit router configuration
    Given a Kanbus project without a router configuration
    When I run "kanbus router plan"
    Then the command should fail with exit code 2
    And stderr should equal "error: issue router is not configured\n"
    And running "kanbus list" in the same project should succeed

  Scenario: The Codex-first router configuration is accepted
    Given a Kanbus project with router configuration:
      """
      router:
        limits:
          project_wip: 2
          review_wip: 1
        forge:
          repository: anthusai/kanbus
        providers:
          codex-default:
            adapter: codex
        classes:
          implementation:
            providers: [codex-default]
      """
    And the project configuration includes:
      """
      statuses:
        - key: backlog
          name: Backlog
          category: To do
          semantic_category: todo
        - key: open
          name: Ready
          category: To do
          semantic_category: todo
          router: true
        - key: in_progress
          name: In progress
          category: In progress
          semantic_category: in_progress
          router: true
        - key: review
          name: Review
          category: In progress
          semantic_category: in_review
          router: true
        - key: blocked
          name: Blocked
          category: In progress
          semantic_category: blocked
          router: true
        - key: closed
          name: Done
          category: Done
          semantic_category: done
          router: true
      """
    When the router configuration is loaded
    Then the configuration should be valid
    And the default provider profile should be "codex-default"
    And provider profile "codex-default" should use command "codex" and no arguments
    And the maximum retry attempts should be 3
    And the router watch interval should be 30 seconds
    And the default forge provider should be "github"
    And the default forge base branch should be "main"
    And the default forge API URL should be "https://api.github.com"
    And the default forge token environment variable should be "GITHUB_TOKEN"

  Scenario: Router GitHub configuration requires one repository
    Given a valid router configuration without a forge repository
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.forge.repository is required\n"

  Scenario: Only GitHub is supported as the initial router forge
    Given a valid router configuration with forge provider "gitlab"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.forge.provider must be github\n"

  Scenario: Forge base branch, API URL, and token environment variable can be overridden
    Given a valid router configuration with forge repository "anthusai/kanbus" and base branch "develop"
    And the forge API URL is "https://github.example.test/api/v3"
    And the forge token environment variable is "KANBUS_GITHUB_TOKEN"
    When the router configuration is loaded
    Then the configuration should be valid
    And the forge should use base branch "develop"
    And the forge should use API URL "https://github.example.test/api/v3"
    And the forge should read credentials only from environment variable "KANBUS_GITHUB_TOKEN"

  Scenario: Forge credentials are not read from a fallback environment variable
    Given the forge token environment variable is "KANBUS_GITHUB_TOKEN"
    And "GITHUB_TOKEN" is also set to "wrong-token"
    When the router forge client is initialized
    Then the client should read credentials only from "KANBUS_GITHUB_TOKEN"

  Scenario: The router watch interval must be a positive duration
    Given a valid router configuration with watch interval "0s"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.watch_interval must be a positive duration\n"

  Scenario: Router configuration must be a mapping
    Given a Kanbus project with router configuration "router: []"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router must be a mapping\n"

  Scenario Outline: Unknown router fields are rejected
    Given a Kanbus project with router configuration field "<field>"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.<field> is an unknown field\n"

    Examples:
      | field       |
      | poll_seconds|
      | fallback    |

  Scenario Outline: Router WIP limits must be positive integers
    Given a valid router configuration with "<field>" set to "<value>"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.limits.<field> must be a positive integer\n"

    Examples:
      | field       | value |
      | project_wip | 0     |
      | project_wip | -1    |
      | review_wip  | 1.5   |

  Scenario: Review WIP cannot exceed project WIP
    Given a valid router configuration with project WIP 1 and review WIP 2
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.limits.review_wip must not exceed project_wip\n"

  Scenario: The router accepts only the Codex and OpenCode adapters
    Given a valid router configuration with provider profile "claude-default" using adapter "claude"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.providers.claude-default.adapter must be codex or opencode\n"

  Scenario: An OpenCode profile selects a Bedrock model and environment
    Given a valid router configuration with provider profile "gpt-oss-bedrock" using adapter "opencode"
    And provider profile "gpt-oss-bedrock" has model "amazon-bedrock/openai.gpt-oss-20b-1:0" and environment {"AWS_REGION": "us-east-1"}
    When the router configuration is loaded
    Then the configuration should be valid
    And provider profile "gpt-oss-bedrock" should use command "opencode" and no arguments
    And provider profile "gpt-oss-bedrock" should use model "amazon-bedrock/openai.gpt-oss-20b-1:0"

  Scenario: A class route must reference configured provider profiles
    Given a valid router configuration with class "implementation" using provider profiles "missing"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.classes.implementation.providers references undefined provider profile \"missing\"\n"

  Scenario: A class route must have an ordered nonempty provider profile list
    Given a valid router configuration with class "implementation" using provider profiles ""
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.classes.implementation.providers must be a nonempty list\n"

  Scenario: Forge repository must use owner and repository components
    Given a valid router configuration with forge repository "kanbus"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.forge.repository must use owner/repository format\n"

  Scenario: Forge token environment variable must be an environment variable name
    Given a valid router configuration with forge token environment variable "abc-token"
    When the router configuration is loaded
    Then the command should fail with exit code 1
    And stderr should equal "error: router.forge.token_env must be a valid environment variable name\n"

  Scenario: Provider command and arguments override the Codex executable for isolated tests
    Given a valid router configuration with provider profile "codex-test" using adapter "codex"
    And provider profile "codex-test" has command "/tmp/fake-codex" and arguments ["--fixture", "success"]
    When the router configuration is loaded
    Then the configuration should be valid
    And provider profile "codex-test" should use command "/tmp/fake-codex" and arguments ["--fixture", "success"]
