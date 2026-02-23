import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const BeadsCompatibilityPage = () => {
  return (
    <Layout>
      <Hero
        title="Beads Compatibility"
        subtitle="Instant Kanban board for your existing Beads projects. No migration required."
        eyebrow="Integrations"
      />

      <div className="space-y-12">
        <Section
          title="Instant Kanban Board"
          subtitle="Visualize your Beads issues immediately."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Zero Conversion Required</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                You don't need to convert your data to get a modern project board. Kanbus reads 
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.beads/issues.jsonl</code> directly.
              </p>
              <p>
                Just type <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">kanbus console</code> (or <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">kbsc</code>) in your project root, 
                or install the VS Code extension. You'll get a fully interactive Kanban board instantly, without changing a single file format.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="High Performance CLI"
          subtitle="Faster operations, zero overhead."
          variant="alt"
        >
          <div className="space-y-6">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Bypass the Bottlenecks</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Avoid the hassles of SQLite server syncing and performance overhead. The Kanbus CLI is written in Rust 
                  and operates directly on your data files with blazing speed.
                </p>
                <CodeBlock label="Instant filtering">{"kanbus list --status open --assignee @me"}</CodeBlock>
                <p>
                  Use the CLI with your agents for rapid context gathering and updates, all while maintaining full compatibility 
                  with your existing Beads tooling.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Risk-Free Migration"
          subtitle="A smooth path forward."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Stay Flexible</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                There's no "big bang" migration. You can stay with the Beads format as long as you want 
                while enjoying the benefits of the Kanbus board and CLI.
              </p>
              <p>
                When you're ready to switch formats entirely, it's a simple operation—but you don't have to do it 
                to get value today.
              </p>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default BeadsCompatibilityPage;
