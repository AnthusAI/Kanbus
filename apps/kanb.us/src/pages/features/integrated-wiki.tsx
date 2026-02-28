import * as React from "react";
import { Layout, Section, Hero, FeaturePictogram } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const IntegratedWikiPage = () => {
  return (
    <Layout>
      <Hero
        title="Integrated Wiki"
        subtitle="Generate dynamic documentation from your issues. Tables, queries, and live data—all from Markdown."
        bottomPane={
          <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
            <FeaturePictogram type="integrated-wiki" />
          </div>
        }
      />

      <div className="space-y-12">
        <Section
          title="Wiki Pages from Markdown"
          subtitle="Write documentation that stays in sync with your project."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus wiki pages are just Markdown files stored in your project directory. Add special directives to your Markdown to embed dynamic data—issue tables, status summaries, priority queues, or custom queries—and Kanbus renders them automatically.
              </p>
              <p>
                Everything is version controlled. Your documentation lives alongside your code and issues, so changes to the project automatically flow into your wiki without manual updates.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Dynamic Query Tables"
          subtitle="Embed live project data directly in your documentation."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Query Issues</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Use declarative syntax to filter and display issues. Show all open bugs, list tasks assigned to a team member, or create a dashboard of high-priority items. The table updates automatically whenever any issue changes.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Custom Columns</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Choose which fields to display: ID, title, assignee, status, priority, labels, or custom properties. Hide columns you don't need, or create multiple tables with different views of the same data.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Pre-built Reports"
          subtitle="Common queries ready to use."
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Status Summary</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Show a table with row for each status and count of issues in each. Perfect for dashboards, status pages, and sprint reviews. Updates in real time as your team moves issues through the workflow.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Issues by Assignee</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Create a matrix showing team members and their open tasks. See at a glance who has the most work in progress or who might need help from the team.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">High Priority Queue</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Focus on what matters now. See all high and critical priority issues in a single table, sorted by status and updated in real time.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Blocked Issues</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Display all issues that have dependencies or are marked as blocked. Know immediately when something is preventing progress and who needs help unblocking.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Issue Details & Hierarchy"
          subtitle="Render rich issue information in your documentation."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Embed full issue details—description, comments, attachments, and metadata—directly in a wiki page. Display parent-child relationships as hierarchical lists, showing which tasks are part of larger epics and features.
              </p>
              <p>
                Create documentation that tells the full story of your project: the big picture from epics down to the granular work that makes it happen.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Dependency Visualization"
          subtitle="Map out issue relationships."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                When issues depend on each other, render those relationships as clear lists or trees. Show dependency chains, critical paths, and blockers. Everyone can see how pieces fit together.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Epic Progress Tracking"
          subtitle="See your roadmap at a glance."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Display epics with counts of total, completed, and in-progress child issues. Show progress bars or completion percentages. Keep stakeholders informed about what's done, what's in flight, and what's coming next.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Living Documentation"
          subtitle="Your wiki evolves with your project."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Static documentation goes stale. With Kanbus, every wiki page is regenerated on demand from your live project data. When issues change, your documentation updates automatically. When you promote a task or close an epic, everyone can see it reflected immediately in the wiki.
              </p>
              <p>
                No more hunting down outdated charts or status reports. Your wiki is always current.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Learn More"
          subtitle="Master dynamic documentation with Kanbus."
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                The integrated wiki makes it easy to keep your team informed and aligned. From roadmaps and dashboards to detailed reports and dependency maps, your documentation stays in perfect sync with your project.
              </p>
              <a 
                href="/docs/features/integrated-wiki" 
                className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95"
              >
                Read the Documentation →
              </a>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default IntegratedWikiPage;
