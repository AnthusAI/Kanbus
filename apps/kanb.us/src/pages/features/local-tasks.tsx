import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const LocalTasksPage = () => {
  return (
    <Layout>
      <Hero
        title="Local Tasks"
        subtitle="Keep personal or exploratory issues on your machine without committing them—then promote them to the shared project when they're ready."
        eyebrow="Features"
      />

      <div className="space-y-12">
        <Section
          title="Private Work, Shared Repository"
          subtitle="Not every task belongs in version control."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Use Git's Own Rules</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus stores shared issues in <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project/issues/</code>,
                which is committed to the repository. Local tasks live in a sibling directory,
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project-local/issues/</code>,
                which Kanbus automatically adds to <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.gitignore</code>.
              </p>
              <p>
                Both directories are indexed together. <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">kanbus list</code> shows
                everything by default—shared and local—but the local files never leave your machine
                unless you explicitly promote them.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Creating Local Issues"
          subtitle="One flag is all it takes."
          variant="alt"
        >
          <div className="space-y-6">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">kanbus create --local</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Add <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">--local</code> to
                  any create command. Kanbus writes the issue to
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project-local/issues/</code> and
                  ensures that directory is in your <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.gitignore</code>.
                </p>
                <CodeBlock label="Create a local task">{"kanbus create --local \"Spike: try the new auth library\""}</CodeBlock>
                <p>
                  If <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project-local/</code> doesn't
                  exist yet, Kanbus creates it and writes a
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project-local/</code> entry
                  to your root <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.gitignore</code>
                  —only once, even if you run the command many times.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Filtering the List"
          subtitle="Focus on shared work, local work, or both."
        >
          <div className="space-y-6">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Default: everything</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Without any flags, <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">kanbus list</code> combines
                  shared and local issues in one view so you have full context while you work.
                </p>
                <CodeBlock label="Show everything">{"kanbus list"}</CodeBlock>
              </CardContent>
            </Card>

            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">--no-local: shared only</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Use <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">--no-local</code> to
                  suppress local issues—useful when you want to see exactly what's committed to the repository,
                  or when sharing a listing with a teammate.
                </p>
                <CodeBlock label="Shared issues only">{"kanbus list --no-local"}</CodeBlock>
              </CardContent>
            </Card>

            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">--local-only: your personal backlog</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Use <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">--local-only</code> to
                  see just your private tasks—a quick way to review what's on your personal plate.
                </p>
                <CodeBlock label="Local issues only">{"kanbus list --local-only"}</CodeBlock>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Promoting and Localizing"
          subtitle="Move issues between local and shared at any time."
          variant="alt"
        >
          <div className="space-y-6">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">kanbus promote</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  When a local task is ready to be shared with the team, promote it. Kanbus moves the
                  file from <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project-local/issues/</code> to
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project/issues/</code>.
                  The identifier and all content stay the same—it's just a file move.
                </p>
                <CodeBlock label="Move to shared">{"kanbus promote kanbus-a1b2c3"}</CodeBlock>
              </CardContent>
            </Card>

            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">kanbus localize</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Pull a shared issue back to local when you want to work on it privately—for example,
                  a speculative rewrite or a task you've taken off the public board temporarily.
                  Kanbus moves it from <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project/issues/</code> to
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project-local/issues/</code> and
                  ensures <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.gitignore</code> is updated.
                </p>
                <CodeBlock label="Move to local">{"kanbus localize kanbus-a1b2c3"}</CodeBlock>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="How the .gitignore Works"
          subtitle="Kanbus manages the ignore entry for you."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Automatic and Idempotent</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                The first time you create a local issue or localize a shared one, Kanbus appends
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project-local/</code> to
                your repository's root <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.gitignore</code>.
                If the entry is already there, nothing changes. If the file doesn't end with a newline,
                Kanbus adds one before appending the entry.
              </p>
              <CodeBlock label="What Kanbus adds to .gitignore">{"project-local/"}</CodeBlock>
              <p>
                You can also set this up ahead of time with
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">kanbus init --local</code>,
                which creates the <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project-local/issues/</code> directory
                and the gitignore entry in one step.
              </p>
              <CodeBlock label="Set up local tasks directory at init time">{"kanbus init --local"}</CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Beads Mode"
          subtitle="Local tasks work with .beads projects too."
          variant="alt"
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">A Separate Local File</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                When working with a Beads-backed project (
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.beads/issues.jsonl</code>),
                local tasks are stored in a separate file that you manage independently via
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.gitignore</code>.
                The two streams are combined when listing, so your agents see everything in one place.
              </p>
              <p>
                The same <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">--local-only</code> and
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">--no-local</code> flags
                work identically regardless of whether the project uses native Kanbus storage or Beads.
              </p>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default LocalTasksPage;
