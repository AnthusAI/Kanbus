import * as React from "react";
import { DocsLayout, CodeBlock } from "../../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { PageProps } from "gatsby";

const DocsJiraSyncPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Jira Sync</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Pull issues from Jira seamlessly into your local Git repository.
          </p>
        </div>

        <div className="mt-6">
          <a 
            href="/features/jira-sync" 
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground transition-colors"
          >
            <span>←</span>
            <span>Back to Jira Sync feature page</span>
          </a>
        </div>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-6">
          <p>
            If your organization uses Jira, you don't have to choose between corporate compliance and a fast developer experience. The Kanbus Jira Sync allows you to safely pull issues down to your local <code>project/issues/</code> directory as JSON files, enabling you to use the fast Kanbus CLI and UI for your daily work.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Setup and Configuration
          </h2>
          <p>First, you need to tell Kanbus how to connect to your Jira instance. Add the <code>jira</code> configuration block to your <code>.kanbus.yml</code>:</p>
          <CodeBlock label="Terminal">
{`# .kanbus.yml
jira:
  url: https://yourcompany.atlassian.net
  project_key: AQA
  sync_direction: pull
  type_mappings:
    Story: story
    Bug: bug
    Task: task
    Workstream: epic`}
          </CodeBlock>

          <p className="mt-6">Next, ensure your credentials are set via environment variables (in your shell or a <code>.env</code> file):</p>
          <CodeBlock label="Terminal">
{`export JIRA_API_TOKEN=your-atlassian-api-token
export JIRA_USER_EMAIL=you@yourcompany.com`}
          </CodeBlock>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Usage Workflow
          </h2>
          <p>Once configured, you can invoke the pull command to fetch your issues:</p>
          <CodeBlock label="Terminal">
{`# Preview what will be pulled without writing files
kanbus jira pull --dry-run

# Execute the sync
kanbus jira pull`}
          </CodeBlock>

          <p className="mt-4">
            Issues will be safely written to your <code>project/issues/</code> directory. Rerunning the command will update any existing issues (idempotent). You can view the newly synced issues instantly by running <code>kanbus list</code>.
          </p>
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsJiraSyncPage;
