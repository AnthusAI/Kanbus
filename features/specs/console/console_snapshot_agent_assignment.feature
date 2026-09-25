Feature: Console snapshot resolves the effective agent assignment
  As a console user
  I want each routed issue to carry its resolved agent assignment
  So that I can see which agent will work on it without secrets reaching the browser

  Background:
    Given a Kanbus project with router configuration:
      """
      router:
        limits:
          project_wip: 3
          review_wip: 2
        forge:
          repository: anthusai/kanbus
        workflow:
          pending: open
          active: in_progress
          review: review
          blocked: blocked
          terminal: [closed]
        providers:
          codex-default:
            adapter: codex
            args: ["--api-key", "sk-secret"]
            env:
              OPENAI_API_KEY: sk-live-secret
          plain:
            adapter: codex
          bedrock:
            adapter: opencode
            model: "amazon-bedrock/openai.gpt-oss-20b-1:0"
            service_tier: flex
        classes:
          implementation:
            providers: [codex-default]
          ordered:
            providers: [bedrock, plain]
      """

  Scenario: A class label resolves to its first provider and shows only the platform
    Given the project has issue "kbs-901" with labels "agent-class:implementation"
    When I build a console snapshot directly
    Then the snapshot issue "kbs-901" agent_assignment should equal:
      """
      {
        "kind": "class",
        "name": "implementation",
        "provider_profile": "codex-default",
        "effective": {"platform": "codex"}
      }
      """

  Scenario: A provider label shows the model and service tier
    Given the project has issue "kbs-902" with labels "agent-provider:bedrock"
    When I build a console snapshot directly
    Then the snapshot issue "kbs-902" agent_assignment should equal:
      """
      {
        "kind": "provider",
        "name": "bedrock",
        "provider_profile": "bedrock",
        "effective": {
          "platform": "opencode",
          "model": "amazon-bedrock/openai.gpt-oss-20b-1:0",
          "settings": {"service_tier": "flex"}
        }
      }
      """

  Scenario: A class with several providers resolves to the first one listed
    Given the project has issue "kbs-903" with labels "agent-class:ordered"
    When I build a console snapshot directly
    Then the snapshot issue "kbs-903" agent_assignment should equal:
      """
      {
        "kind": "class",
        "name": "ordered",
        "provider_profile": "bedrock",
        "effective": {
          "platform": "opencode",
          "model": "amazon-bedrock/openai.gpt-oss-20b-1:0",
          "settings": {"service_tier": "flex"}
        }
      }
      """

  Scenario Outline: Labels that do not name exactly one valid route add no assignment
    Given the project has issue "kbs-904" with labels "<labels>"
    When I build a console snapshot directly
    Then the snapshot issue "kbs-904" should have no agent_assignment

    Examples:
      | labels                                        |
      | agent-class:unknown                           |
      | agent-provider:unknown                        |
      | agent-class:implementation,agent-provider:plain |
      | bug                                           |

  Scenario: Provider secrets never reach the snapshot
    When I build a console snapshot directly
    Then the snapshot router provider "codex-default" arguments should be empty
    And the snapshot router provider "codex-default" environment variable "OPENAI_API_KEY" should be "[redacted]"
    And the snapshot should not contain "sk-secret"
    And the snapshot should not contain "sk-live-secret"
