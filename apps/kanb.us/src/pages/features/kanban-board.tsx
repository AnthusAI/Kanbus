import * as React from "react";
import { Layout, Section, Hero, FullVideoPlayer } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const KanbanBoardPage = () => {
  const featureVideo = getVideoById("kanban-board");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="Kanban Board"
        subtitle="Visualize your workflow in a modern, reactive interface. Drag and drop issues, filter by status, and see the big picture—all without leaving your browser."
        eyebrow="Features"
        bottomPane={
          videoSrc ? (
            <div className="w-full flex justify-center mt-12 mb-8">
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="kanban-board" />
            </div>
          ) : undefined
        }
      />

      <div className="space-y-12">
        <Section
          title="Interactive Workflow"
          subtitle="Manage tasks visually with drag-and-drop simplicity."
        >
          <div className="space-y-6">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Drag & Drop Status Changes</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Move issues between columns to update their status instantly. Drag a task from 
                  <strong>To Do</strong> to <strong>In Progress</strong>, and Kanbus updates the underlying 
                  issue file and git status automatically. No forms, no confirmations—just visual workflow management.
                </p>
                <p>
                  The console runs locally on your machine, serving a fast, responsive interface that 
                  communicates directly with your file system. Everything happens instantly, with zero network latency.
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
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Filter by Assignee</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Click a user avatar to show only their issues. See exactly what everyone on the team 
                  is working on without noise. Perfect for standups, one-on-ones, and focused work sessions.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Type & Priority</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Toggle issue types to focus on Bugs or Epics. Filter by priority to see only 
                  High or Critical items that need immediate attention. Your board adapts to your current needs.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Instant Detail"
          subtitle="Edit issues without losing context."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Side-by-Side Editing</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Click any card to open a detailed slide-out panel. Edit the description, add comments, 
                change assignees, or update fields without leaving the board view. See your changes reflected
                immediately across the entire interface.
              </p>
              <p>
                Changes are saved to disk immediately, ready to be committed with git. Your workflow stays
                smooth and uninterrupted.
              </p>
            </CardContent>
          </Card>
        </Section>
        <Section
          title="Also in VS Code"
          subtitle="Get the same powerful board experience right inside your editor."
          variant="alt"
        >
          <Card className="p-8 bg-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Integrated Development</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Prefer to stay in your IDE? The Kanbus VS Code extension brings the full Kanban board 
                experience into a dedicated tab. Drag, drop, and edit without switching windows.
              </p>
              <p>
                <a href="/features/vscode-plugin" className="text-selected font-semibold hover:underline">
                  Learn more about the VS Code integration →
                </a>
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Learn More"
          subtitle="Master the Kanban board interface."
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Discover all the board features, keyboard shortcuts, and advanced filtering options in the complete documentation.
              </p>
              <a 
                href="/docs/features/kanban-board" 
                className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95"
              >
                Read the Documentation →
              </a>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default KanbanBoardPage;
