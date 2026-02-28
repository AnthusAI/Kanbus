import React from "react";
import { Board } from "@kanbus/ui";
import { KanbanVideoStyles } from "./KanbanVideoStyles";
import { useCurrentFrame, useVideoConfig } from "../remotion-shim";

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

export const IntroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <div
      className="kanban-video"
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        gap: "24px",
        padding: "80px",
        backgroundColor: "#f8fafc",
        boxSizing: "border-box"
      }}
    >
      <KanbanVideoStyles />
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        <div style={{ fontSize: "52px", fontWeight: 700, color: "#0f172a" }}>
          Canvas in one view
        </div>
        <div style={{ fontSize: "22px", color: "#475569", maxWidth: "980px" }}>
          The Kanbus board connects priorities, status, and ownership so teams can
          plan work and execute without leaving the repo.
        </div>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <Board
          columns={boardConfig.statuses.map((status) => status.key)}
          issues={boardIssues}
          priorityLookup={priorityLookup}
          config={boardConfig}
          motion={{ mode: "frame", frame, fps }}
        />
      </div>
    </div>
  );
};
