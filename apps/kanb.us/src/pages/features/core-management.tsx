import * as React from "react";
import { Layout, Section, Hero, FullVideoPlayer, FeaturePictogram } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { VIDEOS, getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const CoreManagementPage = () => {
  const featureVideo = getVideoById("core-management");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="Agent-Ready CLI"
        subtitle="A fast, scriptable CLI tool that lets your coding agents read requirements, update statuses, and track issues natively."
        rightPane={<FeaturePictogram type="core-management" />}
        bottomPane={
          <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
            {videoSrc ? (
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="core-management" />
            ) : null}
          </div>
        }
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
                  and assign ownership in a single line. No modal dialogs, no waiting for page loads—just pure speed.
                </p>
                <p>
                  Need more detail? Open your default text editor directly from the command line to write full descriptions
                  with all the context your team needs. Everything stays in your terminal, exactly where you work.
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
                <h3 className="text-xl font-bold text-foreground">Powerful Filtering</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  List all open issues, or filter down to specific criteria instantly. Kanbus supports filtering
                  by status, priority, type, assignee, and more—giving you exactly the view you need, when you need it.
                </p>
                <p>
                  Output is formatted for readability in the terminal, but can also be piped to other tools
                  as JSON for automation and scripting. Your workflow, your way.
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
                automatically links it to the parent, maintaining clear relationships without manual bookkeeping.
              </p>
              <p>
                When you view an epic, you see all its children and their status at a glance.
                When you view a child task, you see its parent context immediately. No hunting through disconnected lists.
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
                  Move an issue to In Progress and assign it to yourself in one move. No multi-step workflows,
                  no clicking through menus—just instant status updates that keep your project moving forward.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Block & Close</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Mark issues as blocked when you're stuck, or close them when done.
                  Every status change is just a git commit away, keeping your project history clean and traceable.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Learn More"
          subtitle="Dive deeper into core project management features."
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Ready to master Kanbus project management? Explore the complete guide with examples, workflows, and best practices.
              </p>
              <a 
                href="/docs/features/core-management" 
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

export default CoreManagementPage;
