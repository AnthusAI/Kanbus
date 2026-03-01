import React from "react";
import { Layout, Section, Hero, FullVideoPlayer, FeaturePictogram } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { CodeBlock } from "../../components/CodeBlock";
import { getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const PolicyAsCodePage = () => {
  const video = getVideoById("policy-as-code");
  const videoSrc = video ? getVideoSrc(video.filename) : "";
  const videoPoster = video?.poster ? getVideoSrc(video.poster) : undefined;

  return (
    <Layout>
      <Hero
        eyebrow="New Feature"
        title="Policy as Code"
        subtitle="Kairotic guardrails for agents: enforce hard rules and inject guidance at the right moment, not only in a giant upfront prompt."
        rightPane={<FeaturePictogram type="policy-as-code" />}
        bottomPane={
          videoSrc ? (
            <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="policy-as-code" />
            </div>
          ) : null
        }
      />

      <div className="space-y-12">
        <Section
          title="Guardrails And Guidance"
          subtitle="Policy hooks can block unsafe transitions and coach the next step in the same moment."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus policies are Git-style hooks for issue management. They enforce required process rules, then emit warnings and
                suggestions that help agents recover quickly and stay aligned.
              </p>
              <CodeBlock>
{`Feature: Epic readiness guardrail

  Scenario: Epic needs child issues before ready
    Given the issue type is "epic"
    When transitioning to "ready"
    Then the issue must have at least 1 child issues
    Then explain "Epics represent milestones composed of multiple child issues."
    Then warn "Create at least one child story or task before marking an epic ready."
    Then suggest "If this is one deliverable, model it as a story or task instead of an epic."`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Why Kairos Matters"
          subtitle="Right message, right moment, right context."
          variant="alt"
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Programmatic timing beats prompt overload</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                This feature is about <strong>kairos</strong>: delivering procedural guidance exactly when the context says it matters.
                Agents are more reliable when trigger logic decides <em>when</em> to advise, instead of expecting the model to remember every
                rule from a one-time system prompt.
              </p>
              <p>
                The result is fewer guardrail collisions, lower retry cost, and more consistent execution of standard operating procedures.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Hooks At Workflow Pace"
          subtitle="Guidance runs after show, successful CRUD, list, and ready commands."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                List-level hooks are especially useful in planning loops. For example, a policy can remind agents to keep issue states current
                while they triage and sequence work.
              </p>
              <CodeBlock>
{`Feature: List guidance

  Scenario: Status hygiene reminder
    When listing issues
    Then suggest "Remember to reflect your current status in issue states as you work."

  Scenario: Ready queue reminder
    When listing ready issues
    Then warn "Ready means unblocked and actionable now."`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="CLI Workflow"
          subtitle="Inspect, validate, enforce, and request guidance directly from the terminal."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0">
              <CodeBlock>
{`# Validate policy syntax and structural correctness
kbs policy validate

# Check guardrails on a specific issue
kbs policy check kanbus-123

# Request guidance for a specific issue
kbs policy guide kanbus-123

# Disable guidance for one command
kbs --no-guidance list

# Disable guidance for a session
KANBUS_NO_GUIDANCE=1 kbs show kanbus-123`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Step Library"
          subtitle="Built-in filters, assertions, and guidance steps for practical policy authoring."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <ul className="list-disc pl-5 space-y-2">
                <li><strong>Operation filters:</strong> create, update, close, delete, view, list, ready</li>
                <li><strong>Hierarchy checks:</strong> parent/child status and minimum child count assertions</li>
                <li><strong>Field checks:</strong> required fields, labels, regex title patterns, custom fields</li>
                <li><strong>Guidance steps:</strong> <code>warn</code>, <code>suggest</code>, and attached <code>explain</code> lines</li>
              </ul>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default PolicyAsCodePage;
