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
        subtitle="Focused capabilities for modern development workflows."
        eyebrow="Key Capabilities"
      />

      <div className="space-y-20">
        <Section
          title="The Essentials"
          subtitle="Everything you need to manage projects without leaving your terminal."
        >
          <div className="grid gap-6 md:grid-cols-2">
            <FeatureCard
              title="Core Management"
              description="The speed of CLI, the structure of Jira. Create, track, and update tasks without leaving your terminal. Filter by status, priority, and assignee with powerful query commands."
              href="/features/core-management"
            />
            <FeatureCard
              title="Kanban Board"
              description="Visualize your workflow. Drag and drop issues, filter by status, and see the big picture in a modern, reactive interface."
              href="/features/kanban-board"
            />
          </div>
        </Section>

        <Section
          title="Your Workflow, Your Way"
          subtitle="Flexible tools that adapt to how you actually work."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <FeatureCard
              title="Local Tasks"
              description="Keep private tasks off git and promote them when they are ready to share. Perfect for scratchpad ideas, personal to-dos, or drafting complex tickets before they go public."
              href="/features/local-tasks"
            />
            <FeatureCard
              title="Virtual Projects"
              description="Aggregate issues from multiple repositories into a single view. Query, filter, and track work across your entire stack without context switching."
              href="/features/virtual-projects"
            />
          </div>
        </Section>

        <Section
          title="Connected & Compatible"
          subtitle="Works with the tools and formats you already have."
        >
          <div className="grid gap-6 md:grid-cols-2">
            <FeatureCard
              title="Jira Sync"
              description="Pull Jira issues into your repository so agents always have the full context. No API calls during agent sessions—just fast, local file access."
              href="/features/jira-sync"
            />
            <FeatureCard
              title="Beads Mode"
              description="Seamless compatibility with existing Beads projects. Zero config required—Kanbus detects the format and adapts automatically."
              href="/features/beads-compatibility"
            />
            <FeatureCard
              title="VS Code Plugin"
              description="Manage your project without leaving your code. Full Kanban board integration inside your editor."
              href="/features/vscode-plugin"
            />
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default FeaturesPage;
