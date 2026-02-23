import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const KanbanBoardPage = () => {
  return (
    <Layout>
      <Hero
        title="Kanban Board"
        subtitle="Visualize your workflow. Drag and drop issues, filter by status, and see the big picture in a modern, reactive interface."
        eyebrow="Features"
      />

      <div className="space-y-12">
        <Section
          title="Interactive Workflow"
          subtitle="Manage tasks visually with drag-and-drop simplicity."
        >
          <div className="space-y-6">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Drag & Drop Status Changes</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Move issues between columns to update their status instantly. Drag a task from 
                  <strong>To Do</strong> to <strong>In Progress</strong>, and Kanbus updates the underlying 
                  issue file and git status automatically.
                </p>
                <CodeBlock label="Launch the board">
                  {'kanbus console'}
                </CodeBlock>
                <p>
                  The console runs locally on your machine, serving a fast, responsive interface that 
                  communicates directly with your file system.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Live Filtering"
          subtitle="Slice and dice your board view instantly."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Filter by Assignee</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Click a user avatar to show only their issues. See exactly what everyone on the team 
                  is working on without noise.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Type & Priority</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Toggle issue types to focus on Bugs or Epics. Filter by priority to see only 
                  High or Critical items that need immediate attention.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Instant Detail"
          subtitle="Edit issues without losing context."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Side-by-Side Editing</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Click any card to open a detailed slide-out panel. Edit the description, add comments, 
                change assignees, or update fields without leaving the board view.
              </p>
              <p>
                Changes are saved to disk immediately, ready to be committed with git.
              </p>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default KanbanBoardPage;
