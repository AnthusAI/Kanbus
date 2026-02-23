export type FeatureEntry = {
  title: string;
  description: string;
  href: string;
  eyebrow?: string;
};

export const FEATURE_ENTRIES: FeatureEntry[] = [
  {
    title: "Core Management",
    description: "The speed of CLI, the structure of Jira. Create, track, and update tasks without leaving your terminal.",
    href: "/features/core-management"
  },
  {
    title: "Kanban Board",
    description: "Visualize your workflow. Drag and drop issues, filter by status, and see the big picture in a modern, reactive interface.",
    href: "/features/kanban-board"
  },
  {
    title: "Jira Sync",
    description: "Pull Jira issues into your repository so agents always have the full context.",
    href: "/features/jira-sync"
  },
  {
    title: "Local Tasks",
    description: "Keep private tasks off git and promote them when they are ready to share.",
    href: "/features/local-tasks"
  },
  {
    title: "Beads Mode",
    description: "Seamless compatibility with existing Beads projects. Zero config required.",
    href: "/features/beads-compatibility"
  }
];
