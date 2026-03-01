export type FeatureEntry = {
  title: string;
  description: string;
  href: string;
  eyebrow?: string;
};

export const FEATURE_ENTRIES: FeatureEntry[] = [
  {
    title: "Agent-Ready CLI",
    description: "A fast, scriptable CLI tool that lets your coding agents read requirements, update statuses, and track issues natively.",
    href: "/features/core-management"
  },
  {
    title: "Kanban Board",
    description: "Visualize your workflow in a modern, reactive interface. Drag and drop issues, filter by status, and see the big picture.",
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
    title: "Virtual Projects",
    description: "Aggregate issues from multiple repositories into a single view.",
    href: "/features/virtual-projects"
  },
  {
    title: "Beads Mode",
    description: "Seamless compatibility with existing Beads projects. Zero config required.",
    href: "/features/beads-compatibility"
  },
  {
    title: "VS Code Plugin",
    description: "Manage your project without leaving your code. Full Kanban board integration.",
    href: "/features/vscode-plugin"
  },
  {
    title: "Integrated Wiki",
    description: "Generate dynamic documentation from your issues. Tables, queries, and live data—all from Markdown.",
    href: "/features/integrated-wiki"
  },
  {
    title: "Policy as Code",
    description: "Combine hard guardrails with kairotic, in-the-moment guidance so agents follow procedure without losing flow.",
    href: "/features/policy-as-code",
    eyebrow: "New"
  }
];
