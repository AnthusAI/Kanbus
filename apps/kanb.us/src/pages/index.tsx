import * as React from "react";
import { Layout, Section, Hero } from "../components";
import {
  Board,
  Card,
  CardContent,
  CardHeader,
  TaskDetailPanel,
  type TaskDetailIssue
} from "@kanbus/ui";
import { FEATURE_ENTRIES } from "../content/features";
import { VIDEOS } from "../content/videos";
import { getVideoSrc } from "../lib/getVideoSrc";
import "@kanbus/ui/styles/kanban.css"; // Explicit import

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
      chore: "green",
      "sub-task": "violet"
    }
  };
  const boardColumns = boardConfig.statuses.map((status) => status.key);
  const boardIssues: TaskDetailIssue[] = [
    {
      id: "tsk-1a2b3c",
      title: "Calibrate flux capacitor",
      description: "Tune the 1.21 gigawatt threshold so temporal jumps don't fry the time circuits.",
      type: "epic",
      status: "backlog",
      priority: 2,
      created_at: "2024-12-01T10:00:00Z",
      updated_at: "2024-12-05T16:30:00Z",
      comments: [
        {
          author: "Doc Brown",
          text: "Remember to **shield** the time circuits before the next jump.",
          created_at: "2024-12-02T09:15:00Z"
        }
      ]
    },
    {
      id: "tsk-4d5e6f",
      title: "Stabilize warp core coolant loop",
      type: "task",
      status: "in_progress",
      priority: 1,
      assignee: "ryan",
      description: "Balance dilithium regulation to keep the warp core within safety variance.",
      created_at: "2025-01-04T08:00:00Z",
      updated_at: "2025-01-05T15:45:00Z",
      comments: [
        {
          author: "Geordi",
          text: "Coolant injectors show **micro fractures**—recommend swapping before redline.",
          created_at: "2025-01-04T12:00:00Z"
        },
        {
          author: "Data",
          text: "Projected efficiency gain: 11.3% once injector lattice is re-aligned.",
          created_at: "2025-01-04T18:20:00Z"
        }
      ]
    },
    {
      id: "tsk-7g8h9i",
      title: "Diagnose tachyon scanner drift",
      type: "bug",
      status: "in_progress",
      priority: 1,
      description: "Isolate tachyon interference that's skewing long-range sensor readings.",
      created_at: "2025-01-02T13:00:00Z"
    },
    {
      id: "tsk-0j1k2l",
      title: "Ship holodeck safety interlocks",
      type: "task",
      status: "closed",
      priority: 3,
      description: "Package the holodeck override kit so safety interlocks deploy on load.",
      created_at: "2024-11-15T17:00:00Z",
      updated_at: "2024-11-18T09:00:00Z",
      closed_at: "2024-11-20T14:45:00Z"
    },
    {
      id: "tsk-1a2b3c-1",
      title: "Align temporal coils for flux channel",
      type: "sub-task",
      status: "backlog",
      priority: 3,
      parent: "tsk-1a2b3c",
      description: "Fine\u2011tune coil phasing to reduce chrono jitter before the next jump.",
      created_at: "2024-12-03T10:30:00Z"
    }
  ];

  const priorityLookup = {
    1: "high",
    2: "medium",
    3: "low"
  };

  const [collapsedColumns, setCollapsedColumns] = React.useState<Set<string>>(new Set());
  const [selectedIssueId, setSelectedIssueId] = React.useState<string | null>(null);
  const [focusedIssueId, setFocusedIssueId] = React.useState<string | null>(null);
  const [isMaximized, setIsMaximized] = React.useState(false);
  const selectedIssue =
    boardIssues.find((issue) => issue.id === selectedIssueId) ?? null;

  const toggleColumn = (column: string) => {
    const next = new Set(collapsedColumns);
    if (next.has(column)) {
      next.delete(column);
    } else {
      next.add(column);
    }
    setCollapsedColumns(next);
  };

  const handleSelectIssue = (issue: TaskDetailIssue) => {
    if (process.env.NODE_ENV !== "production") {
      console.log("[homepage] select issue", issue.id);
    }
    setSelectedIssueId(issue.id === selectedIssueId ? null : issue.id);
  };
  const handleFocusIssue = (issueId: string) => {
    setFocusedIssueId((prev) => (prev === issueId ? null : issueId));
  };

  const introVideo = VIDEOS[0] ?? null;
  const introPoster = introVideo?.poster ? getVideoSrc(introVideo.poster) : undefined;
  const introSrc = introVideo ? getVideoSrc(introVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="Track issues in your repository"
        subtitle="...where your agents can participate."
        eyebrow="Kanbus"
        actions={
          <>
            <a
              href="/getting-started"
              className="rounded-full bg-selected px-6 py-3 text-sm font-semibold text-background shadow-none hover:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-selected transition-all"
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

      <div className="mx-auto max-w-3xl px-6 lg:px-8 text-center pb-24">
        <p className="text-xl leading-8 text-muted font-medium">
          Kanbus brings project management to your source code. Treat issues as files, track work with Git, and let AI agents participate directly in your workflow without the complexity of external databases.
        </p>
        <p className="mt-6 text-base text-muted/80">
          Already using Beads? Get an instant Kanban board with zero migration.
        </p>
      </div>

      <div className="space-y-24">
        <Section
          title="Realtime Kanban Board"
          subtitle="The board you already use, rendered as a lightweight, shareable view."
        >
          <div className="kanban-snapshot-container">
            <div className={`layout-frame gap-4 ${isMaximized ? "detail-maximized" : ""} flex flex-col lg:flex-row`}>
              <div className="layout-slot layout-slot-board">
                <Board
                  columns={boardColumns}
                  issues={boardIssues}
                  priorityLookup={priorityLookup}
                  config={boardConfig}
                  onSelectIssue={handleSelectIssue}
                  selectedIssueId={selectedIssueId}
                  collapsedColumns={collapsedColumns}
                  onToggleCollapse={toggleColumn}
                  detailOpen={Boolean(selectedIssueId)}
                />
              </div>

              <TaskDetailPanel
                task={selectedIssue}
                allIssues={boardIssues}
                columns={boardColumns}
                priorityLookup={priorityLookup}
                config={boardConfig}
                apiBase=""
                isOpen={Boolean(selectedIssue)}
                isVisible={Boolean(selectedIssue)}
                navDirection="none"
                widthPercent={42}
                layout="auto"
                onClose={() => setSelectedIssueId(null)}
                onToggleMaximize={() => setIsMaximized((prev) => !prev)}
                isMaximized={isMaximized}
                onAfterClose={() => undefined}
                onFocus={handleFocusIssue}
                focusedIssueId={focusedIssueId}
                onNavigateToDescendant={handleSelectIssue}
              />
            </div>
          </div>
        </Section>

        <Section
          title="See it in action"
          subtitle="A quick elevator pitch covering what Kanbus is and everything it can do."
        >
          <div className="max-w-4xl mx-auto">
            <div className="rounded-2xl overflow-hidden shadow-card bg-card">
              <video
                controls
                preload="metadata"
                playsInline
                src={introSrc}
                poster={introPoster}
                style={{
                  width: "100%",
                  display: "block",
                  borderRadius: "14px",
                  background: "rgba(0, 0, 0, 0.75)",
                }}
              />
            </div>
          </div>
        </Section>

        <Section
          title="Features"
          subtitle="Focused capabilities that make Kanbus practical for daily work."
          variant="alt"
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
                <h3 className="text-xl font-bold text-foreground">Rust CLI</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                The preferred way to run Kanbus. High-performance binary for CI/CD pipelines and large repositories.
                Install via Cargo or download a pre-built binary.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Python CLI</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Alternative implementation available via PyPi. Perfect for scripting, local workflows, and
                integrating with Python-based AI tools.
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
