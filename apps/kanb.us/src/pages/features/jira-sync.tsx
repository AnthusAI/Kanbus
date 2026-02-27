import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const JiraSyncPage = () => {
  return (
    <Layout>
      <Hero
        title="Jira Sync"
        subtitle="Pull Jira issues into your repository so coding agents always have full context—no API calls, no MCP tools, just files."
        eyebrow="Integrations"
      />

      <div className="space-y-12">
        <Section
          title="Context Where Agents Can See It"
          subtitle="Coding agents work best when project context lives alongside code."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">From Jira to Files in One Command</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus bridges Jira and your local repository by pulling issues down as plain JSON files.
                Once synced, your coding agents can read every issue, comment, assignee, and priority
                directly from the filesystem—the same way they read your source code.
              </p>
              <p>
                No MCP server. No API credentials wired into the agent. No round-trip calls during a
                session. The context is simply there, in the repository, versioned alongside your work.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="One Command to Sync"
          subtitle="Pull your entire Jira project with a single command."
          variant="alt"
        >
          <div className="space-y-6">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">kanbus jira pull</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Run the pull command from any directory inside your repository. Kanbus reads your
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.kanbus.yml</code>
                  for the Jira connection details and fetches every issue in the configured project.
                </p>
                <CodeBlock label="Pull all issues">{"kanbus jira pull"}</CodeBlock>
                <p>
                  Use <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">--dry-run</code> to
                  preview what would be written without touching any files.
                </p>
                <CodeBlock label="Preview without writing">{"kanbus jira pull --dry-run"}</CodeBlock>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Configuration"
          subtitle="Add a jira block to .kanbus.yml—secrets stay in environment variables."
        >
          <div className="space-y-6">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">.kanbus.yml</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Non-secret configuration lives in the committed
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.kanbus.yml</code>
                  file. The
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">type_mappings</code>
                  field lets you translate Jira's issue type names to Kanbus types.
                </p>
                <CodeBlock label=".kanbus.yml">{`jira:
  url: https://yourcompany.atlassian.net
  project_key: AQA
  sync_direction: pull
  type_mappings:
    Story: story
    Bug: bug
    Task: task
    Workstream: epic
    Sub-task: sub-task`}</CodeBlock>
              </CardContent>
            </Card>

            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Environment Variables</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Your API token and email are read from environment variables and never written to disk.
                  Add them to a
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.env</code>
                  file (already in <code className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.gitignore</code>)
                  or export them from your shell.
                </p>
                <CodeBlock label=".env">{`JIRA_API_TOKEN=your-atlassian-api-token
JIRA_USER_EMAIL=you@yourcompany.com`}</CodeBlock>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Idempotent Updates"
          subtitle="Run the sync as often as you like—existing issues are updated, not duplicated."
          variant="alt"
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Safe to Re-run Anytime</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Each synced issue stores the originating Jira key in a
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">custom.jira_key</code>
                field. On subsequent pulls, Kanbus matches by that key and updates the existing file
                in place—title, description, status, comments, and priority all stay current.
              </p>
              <p>
                Kanbus IDs assigned to pulled issues are stable across runs. Parent links are resolved
                to local Kanbus identifiers, so your agents see the full hierarchy without knowing
                anything about Jira's internal structure.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="What Your Agents See"
          subtitle="Plain JSON files that any tool can read."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">No Special Tooling Required</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Synced issues land in
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">project/issues/</code>
                as standard Kanbus JSON files. Any agent that can read your source files can read your
                issues. Use
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">kanbus list</code>,
                <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">kanbus show</code>,
                or just point an agent at the directory and tell it to read the files.
              </p>
              <CodeBlock label="List all synced issues">{"kanbus list"}</CodeBlock>
              <p>
                Because the issues are files in the repository, they travel with the branch, survive
                offline work, and never require a network call during an agent session. The sync step
                happens once; the context is available forever after.
              </p>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default JiraSyncPage;
