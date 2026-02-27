export type VideoEntry = {
  id: string;
  title: string;
  description: string;
  filename: string;
  poster?: string;
};

export const VIDEOS: VideoEntry[] = [
  {
    id: "intro",
    title: "Intro to Kanbus",
    description: "A quick elevator pitch covering what Kanbus is, how files replace the database, why it's built for AI agents, and the three ways to use it.",
    filename: "intro.mp4",
    poster: "intro-poster.jpg"
  },
  {
    id: "local-tasks",
    title: "Local Tasks",
    description: "Keep private tasks off git and promote them when they are ready to share.",
    filename: "local-tasks.mp4",
    poster: "local-tasks-poster.jpg"
  },
  {
    id: "core-management",
    title: "Core Management",
    description: "The speed of CLI, the structure of Jira. Create, track, and update tasks without leaving your terminal.",
    filename: "core-management.mp4",
    poster: "core-management-poster.jpg"
  },
  {
    id: "jira-sync",
    title: "Jira Sync",
    description: "Pull Jira issues into your repository so agents always have the full context.",
    filename: "jira-sync.mp4",
    poster: "jira-sync-poster.jpg"
  },
  {
    id: "kanban-board",
    title: "Kanban Board",
    description: "A beautiful, local web interface for tracking and managing your issues.",
    filename: "kanban-board.mp4",
    poster: "kanban-board-poster.jpg"
  },
  {
    id: "virtual-projects",
    title: "Virtual Projects",
    description: "Aggregate issues from multiple repositories into a single view.",
    filename: "virtual-projects.mp4",
    poster: "virtual-projects-poster.jpg"
  },
  {
    id: "beads-compatibility",
    title: "Beads Mode",
    description: "Seamless compatibility with existing Beads projects. Zero config required.",
    filename: "beads-compatibility.mp4",
    poster: "beads-compatibility-poster.jpg"
  },
  {
    id: "vscode-plugin",
    title: "VS Code Plugin",
    description: "Manage your project without leaving your code. Full Kanban board integration.",
    filename: "vscode-plugin.mp4",
    poster: "vscode-plugin-poster.jpg"
  },
  {
    id: "policy-as-code",
    title: "Policy as Code",
    description: "Define project rules using Gherkin BDD syntax. Enforce workflows, validations, and standards automatically.",
    filename: "policy-as-code.mp4",
    poster: "policy-as-code-poster.jpg"
  }
];

export const getVideoById = (id: string): VideoEntry | undefined =>
  VIDEOS.find((video) => video.id === id);
