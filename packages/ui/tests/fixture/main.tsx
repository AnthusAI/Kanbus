import React from "react";
import { createRoot } from "react-dom/client";
import * as Kanbus from "@kanbus/ui";
import "@kanbus/ui/styles/tokens.css";
import "@kanbus/ui/styles/kanban.css";

interface HostIssue extends Kanbus.KanbanIssue {
  hostOnlyField?: string;
}

declare global {
  interface Window {
    renderCollection: (query?: Kanbus.IssueQuery, view?: "board" | "list") => void;
    filterArticles: (query: Kanbus.IssueQuery) => string[];
    updateIssue: (identifier: string, status: string) => void;
    renderStandalone: () => void;
    selectedIssue?: HostIssue;
    selectedOriginal?: boolean;
    hostReady: boolean;
  }
}

const configuration: Kanbus.KanbanConfig = {
  statuses: [
    { key: "draft", name: "Draft", category: "Active" },
    { key: "review", name: "Editorial review", category: "Active" },
    { key: "published", name: "Published", category: "Done" },
    { key: "open", name: "Open", category: "Active" }
  ],
  categories: [{ name: "Active" }, { name: "Done" }],
  priorities: { 1: { name: "High" }, 2: { name: "Normal" } },
  type_colors: { article: "blue", task: "green" },
  workflows: {
    article: { draft: ["review"], review: ["draft", "published"], published: [] },
    default: { open: [] }
  }
};

let issues: HostIssue[] = [
  { id: "article-1", title: "First article", type: "article", status: "draft", priority: 1,
    hostOnlyField: "original record",
    assignee: "alex", labels: ["newsletter"], parent: "series-1", custom: { score: 8, ready: true },
    comments: [{ author: "alex", created_at: "2026-10-14T00:00:00Z", text: "Hidden text", comment_type: "summary", data: { activity_summary: "Arrange the interview" } }] },
  { id: "article-2", title: "Second article", type: "article", status: "review", priority: 2,
    assignee: "ben", custom: { score: "8" } },
  { id: "article-3", title: "Third article", type: "article", status: "draft", priority: 2,
    assignee: "alex", custom: { score: 12 } },
  { id: "task-1", title: "Other work", type: "task", status: "open", priority: 2 }
];

const root = createRoot(document.getElementById("root")!);
let currentQuery: Kanbus.IssueQuery = {};
let currentView: "board" | "list" = "board";

Object.assign(window, {
  renderCollection(query: Kanbus.IssueQuery = { type: "article" }, view: "board" | "list" = "board") {
    if (!Kanbus.IssueCollection) throw new Error("IssueCollection is not exported");
    currentQuery = query;
    currentView = view;
    root.render(
      <Kanbus.IssueCollection
        issues={issues}
        config={configuration}
        query={query}
        view={view}
        motion={{ mode: "static" }}
        emptyMessage="No matching articles"
        onSelectIssue={(issue) => {
          const hostOnlyField: string | undefined = issue.hostOnlyField;
          Object.assign(window, { selectedIssue: issue, selectedOriginal: issue === issues.find((entry) => entry.id === issue.id) });
          document.getElementById("root")!.dataset.selectedHostField = hostOnlyField;
        }}
      />
    );
  },
  filterArticles(query: Kanbus.IssueQuery) {
    if (!Kanbus.filterIssues) throw new Error("filterIssues is not exported");
    return Kanbus.filterIssues(issues, { ...query, type: "article" }).map((issue) => issue.id);
  },
  updateIssue(id: string, status: string) {
    issues = issues.map((issue) => issue.id === id ? { ...issue, status } : issue);
    window.renderCollection(currentQuery, currentView);
  },
  renderStandalone() {
    root.render(<Kanbus.Board columns={["open"]} issues={issues.filter((issue) => issue.type === "task")}
      priorityLookup={{ 1: "High", 2: "Normal" }} config={configuration} motion={{ mode: "static" }} />);
  },
  hostReady: true
});
