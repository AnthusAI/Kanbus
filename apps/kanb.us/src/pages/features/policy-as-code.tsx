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
        subtitle="Define project rules using Gherkin BDD syntax. Enforce workflows, validations, and standards automatically."
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
          title="Git-Style Hooks for Issue Management"
          subtitle="Enforce your standards automatically."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Just like Git hooks enforce commit standards, Kanbus policies enforce issue management standards. 
                Create <code>.policy</code> files that automatically validate transitions, enforce required fields, 
                and maintain project consistency.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Write Policies in Gherkin"
          subtitle="Use familiar BDD syntax to describe your project rules."
          variant="alt"
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">No Programming Required</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Just write clear, readable scenarios that express exactly what should happen.
              </p>
              <CodeBlock>
{`Feature: Tasks require assignee

  Scenario: Task must have assignee to start
    Given the issue type is "task"
    When transitioning to "in_progress"
    Then the issue must have field "assignee"`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Automatic Enforcement"
          subtitle="Stop bad data before it gets saved."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Clear Error Messages</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Policies run automatically on every issue create and update. When a policy fails, 
                the operation is rejected with a clear error message showing exactly which rule was violated.
              </p>
              <CodeBlock>
{`$ kbs update task-123 --status in_progress

Error: policy violation in require-assignee.policy
  Scenario: Task must have assignee to start
  Failed: Then the issue must have field "assignee"
  issue does not have field "assignee" set`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Rich Step Library"
          subtitle="Built-in steps cover common scenarios out of the box."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <ul className="list-disc pl-5 space-y-2">
                <li><strong>Field validation:</strong> Require assignee, description, labels</li>
                <li><strong>Status transitions:</strong> Control when issues can move between states</li>
                <li><strong>Hierarchy rules:</strong> Enforce parent-child relationships</li>
                <li><strong>Custom patterns:</strong> Validate titles, descriptions with regex</li>
                <li><strong>Aggregate checks:</strong> Ensure all children meet criteria before parent transitions</li>
              </ul>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Examples"
          subtitle="See what you can build."
        >
          <div className="space-y-6">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Require Description for Bugs</h3>
              </CardHeader>
              <CardContent className="p-0">
                <CodeBlock>
{`Feature: Bug reporting standards

  Scenario: Bugs must have detailed description
    Given the issue type is "bug"
    When creating an issue
    Then the description must not be empty`}
                </CodeBlock>
              </CardContent>
            </Card>

            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Epic Completion Rules</h3>
              </CardHeader>
              <CardContent className="p-0">
                <CodeBlock>
{`Feature: Epic workflow

  Scenario: Epic can only close when all children are done
    Given the issue type is "epic"
    When transitioning to "closed"
    Then all child issues must have status "closed"`}
                </CodeBlock>
              </CardContent>
            </Card>

            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Title Conventions</h3>
              </CardHeader>
              <CardContent className="p-0">
                <CodeBlock>
{`Feature: Naming conventions

  Scenario: Bugs must have BUG prefix
    Given the issue type is "bug"
    Then the title must match pattern "^BUG-"`}
                </CodeBlock>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="CLI Tools"
          subtitle="Test and validate policies before they affect your team."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0">
              <CodeBlock>
{`# Check policies against a specific issue
kbs policy check task-123

# List all loaded policies
kbs policy list

# Validate policy file syntax
kbs policy validate`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Zero Configuration"
          subtitle="Just create a policies directory."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Built for Teams and Agents</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Just create a <code>policies/</code> directory in your project and add <code>.policy</code> files. 
                Kanbus automatically discovers and evaluates them. No config files, no registration, no setup.
              </p>
              <p>
                Policies work the same whether a human or an AI agent is managing issues. Define your standards 
                once, and they're enforced consistently across all interactions—CLI, console UI, and programmatic access.
              </p>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default PolicyAsCodePage;
