import * as React from "react";
import { DocsLayout } from "../../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { PageProps } from "gatsby";

const DocsLocalTasksPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Local Tasks</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Create personal, git-ignored tasks without cluttering the team board.
          </p>
        </div>

        <div className="mt-6">
          <a 
            href="/features/local-tasks" 
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground transition-colors"
          >
            <span>←</span>
            <span>Back to Local Tasks feature page</span>
          </a>
        </div>

        <div className="prose prose-slate dark:prose-invert max-w-none text-muted leading-relaxed space-y-6">
          <p>
            Not every thought or task needs to be tracked on the shared team board. Kanbus allows you to create "Local Tasks" which are stored in a <code>project-local/</code> directory that is automatically ignored by Git. These are visible only to you on your machine.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Initialization & Creation
          </h2>
          <p>
            You can initialize the local directory explicitly, but Kanbus will also create it automatically the first time you create a local task.
          </p>
          <Card className="p-4 bg-card-muted/30">
            <CardContent className="p-0">
              <pre className="text-sm font-mono text-foreground leading-relaxed overflow-x-auto whitespace-pre-wrap">
{`# Optional: Explicitly initialize the local directory and .gitignore
kanbus init --local

# Create a local issue (automatically handles setup if needed)
kanbus create --local "Spike: try the new auth library"`}
              </pre>
            </CardContent>
          </Card>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Listing Local Issues
          </h2>
          <p>
            By default, running <code>kanbus list</code> shows both shared and local issues seamlessly. You can isolate the output using flags:
          </p>
          <Card className="p-4 bg-card-muted/30">
            <CardContent className="p-0">
              <pre className="text-sm font-mono text-foreground leading-relaxed overflow-x-auto whitespace-pre-wrap">
{`# Show both shared and local issues
kanbus list

# Show ONLY shared issues
kanbus list --no-local

# Show ONLY local issues
kanbus list --local-only`}
              </pre>
            </CardContent>
          </Card>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Promoting and Localizing
          </h2>
          <p>
            If a local experiment turns into actual team work, you can "promote" it. If a team task becomes something you just want to track personally, you can "localize" it.
          </p>
          <Card className="p-4 bg-card-muted/30">
            <CardContent className="p-0">
              <pre className="text-sm font-mono text-foreground leading-relaxed overflow-x-auto whitespace-pre-wrap">
{`# Move a local issue to the shared team board (project-local/ -> project/)
kanbus promote kanbus-a1b2c3

# Move a shared team issue to your local board (project/ -> project-local/)
kanbus localize kanbus-a1b2c3`}
              </pre>
            </CardContent>
          </Card>
          <p className="mt-4 text-sm italic">Note: Local tasks function perfectly whether you use native Kanbus storage or Beads compatibility mode.</p>
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsLocalTasksPage;
