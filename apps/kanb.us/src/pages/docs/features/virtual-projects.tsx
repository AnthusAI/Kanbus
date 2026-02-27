import * as React from "react";
import { DocsLayout, CodeBlock } from "../../../components";
import { PageProps } from "gatsby";

const DocsVirtualProjectsPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Virtual Projects</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Aggregate issues across multiple repositories into a single unified view.
          </p>
        </div>

        <div className="mt-6">
          <a 
            href="/features/virtual-projects" 
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground transition-colors"
          >
            <span>←</span>
            <span>Back to Virtual Projects feature page</span>
          </a>
        </div>

        <div className="prose prose-slate dark:prose-invert max-w-none text-muted leading-relaxed space-y-6">
          <p>
            If your system spans multiple repositories (like a frontend UI repo and a backend API repo), you shouldn't have to constantly switch directories to see what needs to be done. Kanbus Virtual Projects allow you to define links to sibling repositories so they all appear as one unified project.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Setup
          </h2>
          <p>You can set up virtual projects at the team level via <code>.kanbus.yml</code>, or for your personal local setup using <code>.kanbus.override.yml</code>.</p>
          
          <h3 className="text-xl font-bold text-foreground mt-6 mb-2">Team Configuration (.kanbus.yml)</h3>
          <CodeBlock label="Terminal">
{`project_key: app
virtual_projects:
  api:
    path: ../backend-api
  ui:
    path: ../design-system`}
          </CodeBlock>

          <h3 className="text-xl font-bold text-foreground mt-6 mb-2">Personal Overrides (.kanbus.override.yml)</h3>
          <p>This file should be git-ignored. It additively merges with the main config.</p>
          <CodeBlock label="Terminal">
{`virtual_projects:
  my_lib:
    path: ../experimental-lib`}
          </CodeBlock>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Usage
          </h2>
          <p>Once your paths are configured, your CLI commands automatically aggregate data.</p>
          <CodeBlock label="Terminal">
{`# Lists issues from the primary project AND all virtual projects
kanbus list

# Filter to show ONLY issues from the 'api' virtual project
kanbus list --project api

# You can combine project filters with standard filters
kanbus list --status open --project api`}
          </CodeBlock>
          <p className="mt-4 text-sm italic">
            Note: Paths are relative to the repository root. Virtual project labels cannot match your main <code>project_key</code>. If a path is missing or invalid, Kanbus will fail with a clear descriptive error.
          </p>
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsVirtualProjectsPage;
