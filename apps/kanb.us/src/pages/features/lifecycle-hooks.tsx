import React from "react";
import { Layout, Section, Hero, FeaturePictogram, FullVideoPlayer } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { CodeBlock } from "../../components/CodeBlock";
import { getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const LifecycleHooksPage = () => {
  const featureVideo = getVideoById("lifecycle-hooks");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="Lifecycle Hooks"
        subtitle="Run project-defined logic on Kanbus lifecycle events with a first-class hook engine shared by Python and Rust."
        rightPane={<FeaturePictogram type="lifecycle-hooks" />}
        bottomPane={
          videoSrc ? (
            <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="lifecycle-hooks" />
            </div>
          ) : null
        }
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
                Existing <code className="font-mono">policy DSL</code> semantics are preserved. The built-in provider emits policy guidance on post-operation
                events like <code className="font-mono">create</code>, <code className="font-mono">update</code>, <code className="font-mono">close</code>, <code className="font-mono">delete</code>, <code className="font-mono">show</code>, <code className="font-mono">list</code>, and <code className="font-mono">ready</code>.
              </p>
              <p>
                <code className="font-mono">--no-guidance</code> and <code className="font-mono">KANBUS_NO_GUIDANCE</code> suppress policy guidance only.
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
