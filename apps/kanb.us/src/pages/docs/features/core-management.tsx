import * as React from "react";
import { DocsLayout, CodeBlock } from "../../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { PageProps } from "gatsby";

const DocsCoreManagementPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Core Management</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Manage your project management issues right from your terminal.
          </p>
        </div>

        <div className="mt-6">
          <a 
            href="/features/core-management" 
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground transition-colors"
          >
            <span>←</span>
            <span>Back to Core Management feature page</span>
          </a>
        </div>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-6">
          <p>
            Kanbus provides a fully-featured CLI for managing your issues, epics, and tasks. Because everything is stored as JSON files, your issues are always right alongside your code, meaning you can easily update them using straightforward terminal commands.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Creating Issues
          </h2>
          <p>You can create issues quickly and define relationships (like assigning an issue to an epic) from the command line:</p>
          <CodeBlock label="Terminal">
{`# Create a top-level bug issue with high priority
kanbus create "Fix login race condition" --type bug --priority high

# Create a task underneath an existing epic/parent
kanbus create "Implement backend API" --parent kanbus-a1b2c3`}
          </CodeBlock>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Listing and Filtering
          </h2>
          <p>
            You can list issues, which is especially powerful when using filters. Kanbus can show just the issues assigned to you, specific issue types, or issues in a certain status.
          </p>
          <CodeBlock label="Terminal">
{`# List high-priority bugs assigned to you
kanbus list --type bug --priority high --assignee @me

# Show only open (non-final state) issues
kanbus list --status open

# Output as JSON for machine parsing or scripting
kanbus list --json`}
          </CodeBlock>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Updating the Workflow
          </h2>
          <p>
            When you're ready to start working on an issue, you can use the Kanbus CLI to update its status or assignee, moving it smoothly through your project's workflow.
          </p>
          <CodeBlock label="Terminal">
{`# Automatically move to an "in_progress" state and assign to yourself
kanbus start kanbus-x9y8z7

# Manually update specific fields
kanbus update kanbus-x9y8z7 --status in_progress --assignee "you@example.com"

# Close an issue and optionally leave a comment
kanbus close kanbus-x9y8z7 --comment "Fixed via PR #42"`}
          </CodeBlock>
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsCoreManagementPage;
