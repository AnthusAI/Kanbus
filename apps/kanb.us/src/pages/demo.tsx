import * as React from "react";
import { Layout, Section } from "../components";
import { Board } from "@kanbus/ui";
import { VIDEOS } from "../content/videos";
import { getVideoSrc } from "../lib/getVideoSrc";

const DemoPage = () => {
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

  return (
    <Layout>
      <div className="space-y-12">
        <Section
          title="Kanban + video demo"
          subtitle="A focused page to validate the live Kanban component alongside the rendered intro video."
        >
          <div className="rounded-2xl bg-card p-4 shadow-card">
            <Board
              columns={boardColumns}
              issues={boardIssues}
              priorityLookup={priorityLookup}
              config={boardConfig}
              motion={{ mode: "css" }}
            />
          </div>
        </Section>

        <Section
          title="Intro video"
          subtitle="Rendered with the same Kanban component running in frame-based motion."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2 items-center">
            <div className="space-y-3">
              <h3 className="text-xl font-bold text-foreground">
                {VIDEOS[0]?.title}
              </h3>
              <p className="text-muted leading-relaxed">
                {VIDEOS[0]?.description}
              </p>
            </div>
            <div className="rounded-2xl overflow-hidden shadow-card bg-card">
              <video
                className="w-full h-full"
                controls
                preload="metadata"
                playsInline
                poster={VIDEOS[0]?.poster ? getVideoSrc(VIDEOS[0].poster) : undefined}
                src={getVideoSrc(VIDEOS[0].filename)}
              />
            </div>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default DemoPage;
