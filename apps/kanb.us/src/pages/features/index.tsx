import * as React from "react";
import { Layout, Section, Hero } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const FeatureCard = ({ title, description, href }: { title: string; description: string; href: string }) => (
  <a href={href} className="group h-full block">
    <Card className="p-6 h-full transition-transform group-hover:-translate-y-1">
      <CardHeader className="p-0 mb-3">
        <h3 className="text-xl font-bold text-foreground group-hover:text-selected transition-colors">
          {title} <span className="inline-block transition-transform group-hover:translate-x-1">→</span>
        </h3>
      </CardHeader>
      <CardContent className="p-0 text-muted leading-relaxed">
        {description}
      </CardContent>
    </Card>
  </a>
);

const FeaturesPage = () => {
  return (
    <Layout>
      <Hero
        title="Features"
        subtitle="Focused capabilities that make Kanbus practical for daily work."
      />

      <div className="space-y-20">
        <Section
          title="The Essentials"
          subtitle="A CLI that agents can use, and a Kanban board for you to visualize work."
        >
          <div className="grid gap-6 md:grid-cols-2">
            <FeatureCard
              title="Agent-Ready CLI"
              description="A fast, scriptable CLI tool that lets your coding agents read requirements, update statuses, and track issues natively."
              href="/features/core-management"
            />
            <FeatureCard
              title="Kanban Board"
              description="Visualize your workflow in a modern, reactive interface. Drag and drop issues, filter by status, and see the big picture—all without leaving your browser."
              href="/features/kanban-board"
            />
          </div>
        </Section>

        <Section
          title="Your Workflow, Your Way"
          subtitle="Keep personal work private, then share when ready. Aggregate issues across repositories."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <FeatureCard
              title="Local Tasks"
              description="Keep personal or exploratory issues on your machine without committing them—then promote them to the shared project when they're ready."
              href="/features/local-tasks"
            />
            <FeatureCard
              title="Virtual Projects"
              description="View and manage issues from multiple repositories in a single workspace."
              href="/features/virtual-projects"
            />
          </div>
        </Section>

        <Section
          title="Connected & Compatible"
          subtitle="Integrate with Jira, Beads, and VS Code—no migration required."
        >
          <div className="grid gap-6 md:grid-cols-2">
            <FeatureCard
              title="Jira Sync"
              description="Pull Jira issues into your repository so coding agents always have full context—no API calls, no MCP tools, just files."
              href="/features/jira-sync"
            />
            <FeatureCard
              title="Beads Mode"
              description="Instant Kanban board for your existing Beads projects. No migration required."
              href="/features/beads-compatibility"
            />
            <FeatureCard
              title="VS Code Plugin"
              description="Manage your project without leaving your code. The full Kanbus experience, embedded in your editor."
              href="/features/vscode-plugin"
            />
          </div>
        </Section>

        <Section
          title="Documentation & Knowledge"
          subtitle="Build living documentation that stays in sync with your project."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <FeatureCard
              title="Integrated Wiki"
              description="Generate dynamic documentation from your issues. Tables, queries, and live data—all from Markdown."
              href="/features/integrated-wiki"
            />
            <FeatureCard
              title="Policy as Code"
              description="Define project rules using Gherkin BDD syntax. Enforce workflows, validations, and standards automatically."
              href="/features/policy-as-code"
            />
          </div>
        </Section>

        <Section
          title="Documentation"
          subtitle="Learn how to use each feature in detail."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Ready to dive deeper? Explore the complete documentation for CLI commands, configuration options, and advanced workflows.
              </p>
              <a
                href="/docs"
                className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95"
              >
                View Documentation →
              </a>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default FeaturesPage;
