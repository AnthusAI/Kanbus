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
import { AnimatedPictogram } from "../components/AnimatedPictogram";
import { CodeUiSync } from "../components/CodeUiSync";
import { HoverVideoPlayer } from "../components/HoverVideoPlayer";
import { motion, useInView } from "framer-motion";
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

  const [issues, setIssues] = React.useState<TaskDetailIssue[]>(boardIssues);
  const [collapsedColumns, setCollapsedColumns] = React.useState<Set<string>>(new Set());
  const [selectedIssueId, setSelectedIssueId] = React.useState<string | null>(null);
  const [focusedIssueId, setFocusedIssueId] = React.useState<string | null>(null);
  const [isMaximized, setIsMaximized] = React.useState(false);
  
  const boardSectionRef = React.useRef<HTMLDivElement>(null);
  const isInView = useInView(boardSectionRef, { margin: "-200px" });

  React.useEffect(() => {
    if (!isInView) return;
    
    let moveCount = 0;
    const interval = setInterval(() => {
      setIssues(current => {
        const newIssues = [...current];
        const step = moveCount % 4;
        
        if (step === 0) {
          // Reset
          return boardIssues;
        } else if (step === 1) {
          const idx = newIssues.findIndex(i => i.id === "tsk-4d5e6f");
          if (idx >= 0) newIssues[idx] = { ...newIssues[idx], status: "closed" };
        } else if (step === 2) {
          const idx = newIssues.findIndex(i => i.id === "tsk-1a2b3c");
          if (idx >= 0) newIssues[idx] = { ...newIssues[idx], status: "in_progress" };
        } else if (step === 3) {
          const idx = newIssues.findIndex(i => i.id === "tsk-1a2b3c-1");
          if (idx >= 0) newIssues[idx] = { ...newIssues[idx], status: "in_progress" };
        }
        
        return newIssues;
      });
      moveCount++;
    }, 2500);
    
    return () => clearInterval(interval);
  }, [isInView]);

  const selectedIssue =
    issues.find((issue) => issue.id === selectedIssueId) ?? null;

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
        bottomPane={
          <div className="w-full flex items-center justify-center">
            <CodeUiSync />
          </div>
        }
        actions={
          <>
            <a
              href="/getting-started"
              style={{ backgroundColor: 'var(--text-foreground)', color: 'var(--background)' }}
              className="rounded-full px-6 py-3 text-sm font-semibold shadow-none hover:opacity-80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 transition-all"
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

      <div className="space-y-0">
        <Section
          title="Use Git as a Kanban bus"
          subtitle="Synchronize multiple boards, CLI tools, and AI agents through your repository's commit history. The repo is the message bus."
        >
          <div className="w-full max-w-5xl mx-auto h-[600px]">
            <AnimatedPictogram />
          </div>
        </Section>

        <Section
          title="Realtime Kanban Board"
          subtitle="The board updates in realtime when your agent makes changes, immediately."
        >
          <div className="kanban-snapshot-container h-[550px]" ref={boardSectionRef}>
            <div className={`layout-frame gap-4 ${isMaximized ? "detail-maximized" : ""} flex flex-col lg:flex-row`}>
              <div className="layout-slot layout-slot-board">
                <Board
                  columns={boardColumns}
                  issues={issues}
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
                allIssues={issues}
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
          title="Features"
          subtitle="Focused capabilities that make Kanbus practical for daily work."
        >
          <div className="grid gap-6 md:grid-cols-2">
            {FEATURE_ENTRIES.map((feature) => (
              <a key={feature.href} href={feature.href} className="group block">
                <div className="bg-card rounded-2xl overflow-hidden transition-transform group-hover:-translate-y-1 h-full flex flex-col">
                  {/* Flat Engineering Frame Header */}
                  <div className="flex items-center gap-2 px-4 py-3 bg-column">
                    <div className="w-2.5 h-2.5 rounded-full bg-muted/40"></div>
                    <div className="w-2.5 h-2.5 rounded-full bg-muted/40"></div>
                    <div className="w-2.5 h-2.5 rounded-full bg-muted/40"></div>
                    <div className="ml-2 font-mono text-xs text-muted">kbs {feature.href.split('/').pop()}</div>
                  </div>
                  {/* Video Placeholder / Content */}
                  <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
                    <HoverVideoPlayer
                      src={introSrc} // Placeholder video until specific feature videos exist
                      poster={introPoster}
                    />
                  </div>
                  {/* Feature Text */}
                  <div className="p-6 flex-1 flex flex-col">
                    <h3 className="text-xl font-bold text-foreground mb-3">{feature.title}</h3>
                    <p className="text-muted leading-relaxed flex-1">
                      {feature.description}
                    </p>
                  </div>
                </div>
              </a>
            ))}
          </div>
        </Section>

        <Section
          title="Integrated Wiki"
          subtitle="The forest vs the trees. Live planning documents that render real-time issue data."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8 bg-card">
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
            <Card className="p-8 bg-card">
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
            <Card className="p-8 hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Rust CLI</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                The preferred way to run Kanbus. High-performance binary for CI/CD pipelines and large repositories.
                Install via Cargo or download a pre-built binary.
              </CardContent>
            </Card>
            <Card className="p-8 hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Python CLI</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Alternative implementation available via PyPi. Perfect for scripting, local workflows, and
                integrating with Python-based AI tools.
              </CardContent>
            </Card>
            <Card className="p-8 hover:-translate-y-1 transition-transform">
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
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Successor to Beads</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Inspired by the elegant Beads cognitive framework, but re-engineered for Git. We removed the
                SQLite database, used separate files to eliminate merge conflicts, and adopted standard Jira
                terms to better leverage AI pre-training.
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Vs. Jira</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Your data is local. No web latency, no login screens, and native CLI access for your AI agents
                to read and write tasks. And there are no per-seat costs—it's just your repo.
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
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
