import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const BeadsCompatibilityPage = () => {
  return (
    <Layout>
      <Hero
        title="Beads Compatibility"
        subtitle="Seamless interoperability with the Beads framework. Use Kanbus power on your existing data."
        eyebrow="Integrations"
      />

      <div className="space-y-12">
        <Section
          title="Zero Configuration"
          subtitle="It just works."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Auto-detection</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus automatically detects if your repository uses the Beads format. If it finds
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.beads/issues.jsonl</code>,
                it switches to compatibility mode instantly.
              </p>
              <p>
                No configuration flags, no migration scripts. You can start using Kanbus commands
                on your existing Beads project immediately.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Full CLI Power"
          subtitle="A better interface for your data."
          variant="alt"
        >
          <div className="space-y-6">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Read and Write</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  All Kanbus commands work with Beads data. List issues, view details, create new tasks,
                  and update status—Kanbus handles the underlying file format transparently.
                </p>
                <CodeBlock label="List Beads issues">{"kanbus list --status open"}</CodeBlock>
                <p>
                  You get the speed and ergonomics of the Kanbus CLI while keeping the data format
                  that your existing tools expect.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Best of Both Worlds"
          subtitle="Mix modern features with legacy compatibility."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Local Tasks + Beads</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Even in compatibility mode, you can use Kanbus-exclusive features like Local Tasks.
                Keep your private TODO list in <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.gitignore</code>
                while collaborating on the shared Beads project.
              </p>
              <CodeBlock label="Create a local task in a Beads project">
                {'kanbus create "Private experiment" --local'}
              </CodeBlock>
              <p>
                Kanbus merges both data sources into a single view, giving you a unified dashboard
                for all your work.
              </p>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default BeadsCompatibilityPage;
