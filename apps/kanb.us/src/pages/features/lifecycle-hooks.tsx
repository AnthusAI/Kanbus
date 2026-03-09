import React from "react";
import { Layout, Section, Hero, FeaturePictogram } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { CodeBlock } from "../../components/CodeBlock";

const LifecycleHooksPage = () => {
  return (
    <Layout>
      <Hero
        title="Lifecycle Hooks"
        subtitle="Run project-defined logic on Kanbus lifecycle events with a first-class hook engine shared by Python and Rust."
        rightPane={<FeaturePictogram type="lifecycle-hooks" />}
      />

      <div className="space-y-12">
        <Section
          title="One Engine, Every Boundary"
          subtitle="Before/after hook phases are available across mutating and read operations."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Lifecycle hooks execute at normalized command boundaries: create, update, close, delete,
                comment, dependency edits, promote, localize, show, list, and ready.
              </p>
              <p>
                Before-hooks on mutating operations are fail-closed by default. After-hooks are observer style:
                failures are surfaced as warnings without rolling back successful commands.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Project-Defined Integrations"
          subtitle="Each hook is a command invocation with timeout, blocking mode, cwd, and per-hook env overrides."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0">
              <CodeBlock>
{`hooks:
  enabled: true
  run_in_beads_mode: true
  default_timeout_ms: 5000
  before:
    issue.update:
      - id: validate-ticket
        command: ["./hooks/validate-ticket.sh"]
        timeout_ms: 1200
  after:
    issue.create:
      - id: notify-created
        command: ["./hooks/notify-created.sh"]
        env:
          WEBHOOK_URL: "https://example.invalid/hooks"
    issue.list:
      - id: planner-reminder
        command: ["./hooks/planning-reminder.sh"]`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Unified With Policy Guidance"
          subtitle="Policy as Code guidance now runs through the same lifecycle engine as a built-in hook provider."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Guardrails and custom hooks, same lifecycle model</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Existing policy DSL semantics are preserved. The built-in provider emits policy guidance on post-operation
                events like create, update, close, delete, show, list, and ready.
              </p>
              <p>
                <code>--no-guidance</code> and <code>KANBUS_NO_GUIDANCE</code> suppress policy guidance only.
                External project hooks continue to run unless hooks are globally disabled.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Operator UX"
          subtitle="Inspect and validate hooks directly from the CLI."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0">
              <CodeBlock>
{`# Inspect configured hooks and built-in providers
kbs hooks list

# Validate event bindings, IDs, command paths, and cwd values
kbs hooks validate

# Disable all hooks for one command
kbs --no-hooks list

# Disable all hooks for a session
KANBUS_NO_HOOKS=1 kbs list`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default LifecycleHooksPage;
