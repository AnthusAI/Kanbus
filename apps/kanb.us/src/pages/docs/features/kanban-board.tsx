import * as React from "react";
import { DocsLayout, CodeBlock } from "../../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { PageProps } from "gatsby";

const DocsKanbanBoardPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Kanban Board</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            A beautiful, local web interface for tracking and managing your issues.
          </p>
        </div>

        <div className="mt-6">
          <a 
            href="/features/kanban-board" 
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground transition-colors"
          >
            <span>←</span>
            <span>Back to Kanban Board feature page</span>
          </a>
        </div>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-6">
          <p>
            Sometimes you need a visual representation of your project state. Kanbus includes a fast, 
            local Kanban board interface powered by React and Rust. It reads directly from your local 
            JSON files and updates in real-time as you make changes via the CLI or UI.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Starting the Console
          </h2>
          <p>You can start the Kanban console easily from your terminal. It will open a local web server (usually at <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">http://127.0.0.1:5174/</code>).</p>
          <CodeBlock label="Terminal">
{`# If you are developing locally:
./dev.sh

# Using the pre-compiled binary:
kanbus console`}
          </CodeBlock>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            UI Interactions
          </h2>
          <p>
            Once the board is running, you can open your browser to view it. The interface supports a variety of interactions:
          </p>
          <ul className="list-disc pl-5 space-y-2 mt-4">
            <li><strong>Filtering:</strong> Click on user avatars, toggle issue types (e.g., Bugs, Epics), or filter by priority.</li>
            <li><strong>Editing:</strong> Click on any issue card to open the detail panel, where you can modify the description, assignee, status, and more.</li>
            <li><strong>Real-time Sync:</strong> The board leverages Server-Sent Events (SSE). If you update an issue using the CLI, the board instantly reflects the changes.</li>
          </ul>
          <p className="text-sm text-muted/80 mt-4 italic">
            Note: Drag-and-drop between columns is not currently implemented. Status changes are made via the detail panel or CLI commands, and cards automatically sort into the correct columns.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            CLI Console Helpers
          </h2>
          <p>Kanbus provides special CLI commands to interact with the console UI programmatically, which is exceptionally useful for automation or AI agents.</p>
          <CodeBlock label="Terminal">
{`# Force the UI to focus/open a specific issue
kanbus console focus <issue-id>

# Trigger a reload of the console page
kanbus console reload

# Check the active state/status of the console
kanbus console status`}
          </CodeBlock>
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsKanbanBoardPage;
