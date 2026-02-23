import * as React from "react";
import { Layout, Section, Hero } from "../components";
import { Board, Card, CardContent, CardHeader } from "@kanbus/ui";
import { FEATURE_ENTRIES } from "../content/features";
import { VIDEOS } from "../content/videos";
import { getVideoSrc, getVideosBaseUrl } from "../lib/getVideoSrc";

const IndexPage = () => {
  const boardConfig = {
    statuses: [
      { key: "backlog", name: "Backlog", category: "To do" },
      { key: "in_progress", name: "In Progress", category: "In progress" },
      { key: "closed", name: "Done", category: "Done" }
    ],
    categories: [
      { name: "To do", color: "grey" },
      { name: "In progress", color: "blue" },
      { name: "Done", color: "green" }
    ],
    priorities: {
      1: { name: "high", color: "bright_red" },
      2: { name: "medium", color: "yellow" },
      3: { name: "low", color: "blue" }
    },
    type_colors: {
      epic: "magenta",
      task: "blue",
      bug: "red",
      story: "yellow",
      chore: "green"
    }
  };
  const boardColumns = boardConfig.statuses.map((status) => status.key);
  const boardIssues = [
    {
      id: "tsk-1a2b3c",
      title: "Map release milestones",
      type: "epic",
      status: "backlog",
      priority: 2
    },
    {
      id: "tsk-4d5e6f",
      title: "Wire notifications",
      type: "task",
      status: "in_progress",
      priority: 1,
      assignee: "ryan"
    },
    {
      id: "tsk-7g8h9i",
      title: "Fix sync edge case",
      type: "bug",
      status: "in_progress",
      priority: 1
    },
    {
      id: "tsk-0j1k2l",
      title: "Ship static export",
      type: "task",
      status: "closed",
      priority: 3
    }
  ];
  const priorityLookup = {
    1: "high",
    2: "medium",
    3: "low"
  };

  const introVideo = VIDEOS[0] ?? null;
  const videosBaseUrl = getVideosBaseUrl();
  const canRenderVideo = Boolean(introVideo && videosBaseUrl);
  const introPoster =
    canRenderVideo && introVideo?.poster ? getVideoSrc(introVideo.poster) : undefined;
  const introSrc = canRenderVideo && introVideo ? getVideoSrc(introVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="Track issues in your repository"
        subtitle="where your agents can see it"
        eyebrow="Kanbus"
        actions={
          <>
            <a
              href="/getting-started"
              className="rounded-full bg-selected px-6 py-3 text-sm font-semibold text-background shadow-card hover:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-selected transition-all"
            >
              Get Started
            </a>
            <a
              href="/philosophy"
              className="text-sm font-semibold leading-6 text-foreground hover:text-selected transition-all"
            >
              Learn More <span aria-hidden="true">→</span>
            </a>
          </>
        }
      />

      <p className="text-lg leading-8 text-muted max-w-2xl mx-auto text-center">
        Files are the database. Kanbus keeps your issues, plans, and code in one repository, without the complexity.
        <span className="block mt-4 text-base text-muted/80">
          Already using Beads? Get an instant Kanban board with zero migration.
        </span>
      </p>

      <div className="space-y-12">
        <Section
          title="Features"
          subtitle="Focused capabilities that make Kanbus practical for daily work."
        >
          <div className="grid gap-6 md:grid-cols-2">
            {FEATURE_ENTRIES.map((feature) => (
              <a key={feature.href} href={feature.href} className="group">
                <Card className="p-6 shadow-card transition-transform group-hover:-translate-y-1">
                  <CardHeader className="p-0 mb-3">
                    <h3 className="text-xl font-bold text-foreground">{feature.title}</h3>
                  </CardHeader>
                  <CardContent className="p-0 text-muted leading-relaxed">
                    {feature.description}
                  </CardContent>
                </Card>
              </a>
            ))}
          </div>
        </Section>

        <Section
          title="Intro video"
          subtitle="A quick walkthrough of Canvas and how it ties issues to execution."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2 items-center">
            <div className="space-y-3">
              <h3 className="text-xl font-bold text-foreground">
                {introVideo?.title}
              </h3>
              <p className="text-muted leading-relaxed">
                {introVideo?.description}
              </p>
            </div>
            <div className="rounded-2xl overflow-hidden shadow-card bg-card">
              {canRenderVideo ? (
                <video
                  className="w-full h-full"
                  controls
                  preload="metadata"
                  playsInline
                  poster={introPoster}
                  src={introSrc}
                />
              ) : (
                <p className="p-8 text-muted text-sm text-center">
                  Set GATSBY_VIDEOS_BASE_URL to enable the intro video preview.
                </p>
              )}
            </div>
          </div>
        </Section>

        <Section
          title="Kanban snapshot"
          subtitle="The board you already use, rendered as a lightweight, shareable view."
        >
          <div className="rounded-2xl bg-card p-4 shadow-card">
            <Board
              columns={boardColumns}
              issues={boardIssues}
              priorityLookup={priorityLookup}
              config={boardConfig}
              motion={{ mode: "static" }}
            />
          </div>
        </Section>

        <Section
          title="Files are the database"
          subtitle="Stop syncing your work to a separate silo. Kanbus stores everything in your Git repository."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">One File Per Issue</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Other systems store everything in one big JSONL file, causing constant merge conflicts.
                Kanbus creates a separate JSON file for each issue, so your team (and agents) can work
                in parallel without blocking each other.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">No Friction</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Git hooks should help you, not block you. There is no database server to maintain,
                no background process to crash, and no complex synchronization logic. Each command scans
                the project files directly.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Collision-Free IDs</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Kanbus assigns hash-based unique IDs to avoid collisions during concurrent edits.
                Unlike hierarchical numbering schemes, hash IDs work safely when multiple agents
                create child issues in parallel.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Shared Datastore Support</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Multiple projects can point to a shared data store while keeping project_key per issue
                to prevent collisions. Track work across codebases with centralized visibility and
                per-project namespacing.
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Integrated Wiki"
          subtitle="The forest vs the trees. Live planning documents that render real-time issue data."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">
                  Live Context for Agents
                </h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Use Jinja2 templates to inject live lists of open tasks directly into your planning docs.
                Agents can read these docs to get up to speed instantly on any initiative.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Full Graph Support</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Define dependencies, blockers, and relationships between issues. We support a rich graph
                of associations without the overhead of a graph database.
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Dual Implementation + Web Console"
          subtitle="One behavior specification driving two complete CLIs, plus a web UI server."
        >
          <div className="grid gap-8 md:grid-cols-3">
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Python CLI</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Easy to install via pip. Perfect for scripting, local workflows, and integrating with AI tools.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Rust CLI</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                High-performance binary for CI/CD pipelines and large repositories. 100% behavior parity with
                the Python version.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Web Console</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Single-binary web UI server with embedded React frontend. Download and run—no configuration,
                no separate assets, no npm required.
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Why Kanbus?"
          subtitle="Built for the age of AI-assisted development."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-3">
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Successor to Beads</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Inspired by the elegant Beads cognitive framework, but re-engineered for Git. We removed the
                SQLite database, used separate files to eliminate merge conflicts, and adopted standard Jira
                terms to better leverage AI pre-training.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Vs. Jira</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Your data is local. No web latency, no login screens, and native CLI access for your AI agents
                to read and write tasks. And there are no per-seat costs—it's just your repo.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Vs. Markdown</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                You get structured data (priority, status) where you need it, and free-form Markdown descriptions
                where you want it.
              </CardContent>
            </Card>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default IndexPage;
