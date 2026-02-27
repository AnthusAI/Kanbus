import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const CoreManagementPage = () => {
  return (
    <Layout>
      <Hero
        title="Core Project Management"
        subtitle="The speed of the command line, the structure of Jira, and the simplicity of Markdown."
        eyebrow="Features"
      />

      <div className="space-y-12">
        <Section
          title="Create & Track"
          subtitle="Add tasks without leaving your terminal."
        >
          <div className="space-y-6">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">One Command to Start</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Create tasks, stories, and bugs instantly. Add descriptions with Markdown, set priorities,
                  and assign ownership in a single line. No modal dialogs, no waiting for page loads.
                </p>
                <CodeBlock label="Create a high-priority bug">
                  {'kanbus create "Fix login race condition" --type bug --priority high'}
                </CodeBlock>
                <p>
                  Need more detail? Use <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">--editor</code> to
                  open your default text editor (vim, nano, VS Code) and write a full description.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="View & Filter"
          subtitle="Find exactly what you need with powerful query filters."
          variant="alt"
        >
          <div className="space-y-6">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">kanbus list</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  List all open issues, or filter down to specific criteria. Kanbus supports filtering
                  by status, priority, type, assignee, and more.
                </p>
                <CodeBlock label="List high-priority bugs assigned to me">
                  {'kanbus list --type bug --priority high --assignee @me'}
                </CodeBlock>
                <p>
                  Output is formatted for readability in the terminal, but can also be piped to other tools
                  as JSON using <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">--json</code>.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Hierarchy"
          subtitle="Organize work into Epics and break them down."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Parent-Child Relationships</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Group related tasks under an Epic to track larger initiatives. Creating a child task
                automatically links it to the parent.
              </p>
              <CodeBlock label="Add a task to an epic">
                {'kanbus create "Implement backend API" --parent kanbus-a1b2c3'}
              </CodeBlock>
              <p>
                When you view an epic, you see all its children and their status at a glance.
                When you view a child task, you see its parent context immediately.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Workflow"
          subtitle="Move work forward with clear status transitions."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Start & Stop</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Use <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">kanbus start</code> to
                  move an issue to In Progress and assign it to yourself in one move.
                </p>
                <CodeBlock>{"kanbus start kanbus-x9y8z7"}</CodeBlock>
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Block & Close</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Mark issues as blocked when you're stuck, or close them when done.
                  Every status change is just a git commit away.
                </p>
                <CodeBlock>{"kanbus close kanbus-x9y8z7"}</CodeBlock>
              </CardContent>
            </Card>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default CoreManagementPage;
