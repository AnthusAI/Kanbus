import type * as KanbusTypes from "@kanbus/ui";

export interface HostIssue extends KanbusTypes.KanbanIssue {
  hostOnlyField?: string;
}

export const fixtureConfiguration: KanbusTypes.KanbanConfig = {
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

export const fixtureIssues: HostIssue[] = [
  { id: "article-1", title: "First article", type: "article", status: "draft", priority: 1,
    hostOnlyField: "original record",
    excerpt: "The council met on Tuesday evening to debate the long awaited proposal for the harbor district, hearing from residents, merchants and engineers before adjourning without a vote until the following week.",
    assignee: "alex", labels: ["newsletter"], parent: "series-1", custom: { score: 8, ready: true },
    comments: [{ author: "alex", created_at: "2026-10-14T00:00:00Z", text: "Hidden text", comment_type: "summary", data: { activity_summary: "Arrange the interview" } }] },
  { id: "article-2", title: "Second article", type: "article", status: "review", priority: 2,
    subtitle: "Why the harbor vote slipped a week", assignee: "ben", custom: { score: "8" } },
  { id: "article-3", title: "Third article", type: "article", status: "draft", priority: 2,
    assignee: "alex", custom: { score: 12 } },
  { id: "task-1", title: "Other work", type: "task", status: "open", priority: 2 }
];

