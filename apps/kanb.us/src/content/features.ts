export type FeatureEntry = {
  title: string;
  description: string;
  detailedDescription?: string[];
  href: string;
  eyebrow?: string;
};

export const FEATURE_ENTRIES: FeatureEntry[] = [
  {
    title: "Agent-Ready CLI",
    description: "A fast, scriptable CLI tool that lets your coding agents read requirements, update statuses, and track issues natively.",
    detailedDescription: [
      "Kanbus ships a single binary that handles every project-management operation from your terminal. Create issues, update statuses, assign work, promote local tasks, and query your backlog—all without leaving your shell or opening a browser.",
      "Every command returns structured output that coding agents can parse directly. Agents read requirements with kbs show, update progress with kbs update, and list work with kbs list. No MCP tools, no API tokens—just a CLI that works like any other Unix tool."
    ],
    href: "/features/core-management"
  },
  {
    title: "Kanban Board",
    description: "Visualize your workflow in a modern, reactive interface. Drag and drop issues, filter by status, and see the big picture.",
    detailedDescription: [
      "A local web interface for visualizing and managing your project. Drag issues between columns, filter by status or type, and see your entire backlog at a glance. The board reads directly from your repository files so it always reflects the current state of your working tree.",
      "The board runs as a local server started with kbs console. It supports real-time updates when the gossip layer is active, inline editing of issue fields, and keyboard shortcuts for fast navigation. No cloud account required—your data never leaves your machine."
    ],
    href: "/features/kanban-board"
  },
  {
    title: "Git-Native Storage",
    description: "Your issues are plain JSON files in your repo. No database, no proprietary index--just transparent files you can read, diff, and version like any other code.",
    detailedDescription: [
      "Every issue is a JSON file in your repository's project directory. When you create an issue, Kanbus writes a file. When you update one, it updates that file. There is no background daemon, no SQLite database, and no index to corrupt or rebuild. Your project data is always right there in the working tree, readable by any tool that can open a file.",
      "Because issues live in Git, you get complete change history automatically. Branch your backlog alongside your code, review issue changes in pull requests, and merge project-management updates through the same workflow as everything else. An optional overlay cache keeps listing fast, but it is entirely disposable—delete it any time and Kanbus rebuilds from the files."
    ],
    href: "/features/git-native-storage"
  },
  {
    title: "Realtime Collaboration",
    description: "Instant updates across agents and humans. Lightweight pub/sub messaging keeps everyone in sync without waiting for a pull.",
    detailedDescription: [
      "Kanbus adds an optional pub/sub notification layer so agents and humans learn about changes instantly, without waiting for a git pull. Every mutation publishes a lightweight gossip message. Watchers receive it, update a disposable overlay cache, and the board refreshes in real time.",
      "Two transports are supported out of the box: a Unix domain socket (UDS) broker for same-machine collaboration between tools, and MQTT for LAN or cloud setups. Kanbus can autostart a local Mosquitto broker when configured. The gossip layer is strictly additive—mutations never depend on the broker, and your repository files remain the only source of truth."
    ],
    href: "/features/realtime-collaboration"
  },
  {
    title: "Jira Sync",
    description: "Pull Jira issues into your repository so agents always have the full context.",
    detailedDescription: [
      "Pull Jira issues directly into your repository as local JSON files. Coding agents get full context—titles, descriptions, statuses, priorities—without making API calls or configuring MCP tools. The issues are just files on disk, available the moment the agent starts working.",
      "Sync runs on demand via the CLI. Kanbus maps Jira fields to its own lightweight schema, so your agents work with a consistent format regardless of how your Jira project is configured. Updates flow one way: from Jira into your repo. Your local workflow stays independent."
    ],
    href: "/features/jira-sync"
  },
  {
    title: "Local Tasks",
    description: "Keep private tasks off git and promote them when they are ready to share.",
    detailedDescription: [
      "Keep personal or exploratory issues on your machine without committing them to the shared repository. Local tasks live in a gitignored directory so they never appear in diffs or pull requests. Use them for scratch work, personal reminders, or half-formed ideas that aren't ready for the team.",
      "When a local task is ready to share, promote it to the project directory with a single command. It becomes a regular tracked issue with full history from that point forward. No migration, no copy-paste—just kbs promote and it's part of the project."
    ],
    href: "/features/local-tasks"
  },
  {
    title: "Virtual Projects",
    description: "Aggregate issues from multiple repositories into a single view.",
    detailedDescription: [
      "View and manage issues from multiple repositories in a single workspace. Virtual projects let you define a collection of repos and see all their issues on one board, without moving files or changing directory structures.",
      "This is useful for teams that split work across microservices or monorepo boundaries but still want a unified backlog. The CLI and console both support virtual project views, so you get the same filtering and status tracking you would in a single repo."
    ],
    href: "/features/virtual-projects"
  },
  {
    title: "Beads Mode",
    description: "Seamless compatibility with existing Beads projects. Zero config required.",
    detailedDescription: [
      "If you already have a project using the Beads cognitive framework, Kanbus can read it directly. Point the CLI or console at a Beads repository and get an instant Kanban board, status filtering, and all the standard Kanbus features—no migration and no configuration required.",
      "Beads mode automatically detects the Beads directory structure and maps its issue format to the Kanbus schema. You can continue using Beads tools alongside Kanbus, or gradually transition to Kanbus-native storage at your own pace."
    ],
    href: "/features/beads-compatibility"
  },
  {
    title: "VS Code Plugin",
    description: "Manage your project without leaving your code. Full Kanban board integration.",
    detailedDescription: [
      "The full Kanbus Kanban board embedded in your editor as a VS Code extension. View issues, drag between columns, and update statuses without switching windows. The board renders in a webview panel alongside your code.",
      "The plugin communicates with the same local Kanbus server used by the standalone console, so changes made in VS Code are immediately visible in the terminal and vice versa. When the gossip layer is active, updates from other agents appear in real time."
    ],
    href: "/features/vscode-plugin"
  },
  {
    title: "Integrated Wiki",
    description: "Generate dynamic documentation from your issues. Tables, queries, and live data—all from Markdown.",
    detailedDescription: [
      "Build living documentation that stays in sync with your project. The wiki engine renders Markdown files with embedded queries that pull live data from your issues—tables of open tasks, status breakdowns, dependency graphs, and more.",
      "Wiki pages live in your repository alongside your issues and code. They are versioned, diffable, and reviewable in pull requests. Agents can read wiki pages for context or generate new documentation as part of their workflow."
    ],
    href: "/features/integrated-wiki"
  },
  {
    title: "Policy as Code",
    description: "Combine hard guardrails with kairotic, in-the-moment guidance so agents follow procedure without losing flow.",
    detailedDescription: [
      "Define project rules and workflows using Gherkin BDD syntax, stored as .feature files in your repository. Policies can enforce hard constraints—like requiring a description before an issue moves to In Progress—or provide soft guidance that agents receive at the right moment.",
      "Kairotic policies fire contextually: when an agent tries to perform an action, the policy engine evaluates the relevant rules and returns guidance inline. This keeps agents on track without front-loading a massive prompt. Policies are versioned in Git and reviewable like any other code."
    ],
    href: "/features/policy-as-code"
  },
  {
    title: "Agile Metrics",
    description: "Track filter-aware issue counts and status/type breakdowns in a focused metrics view built into the Kanbus console.",
    detailedDescription: [
      "A dedicated metrics panel in the Kanbus console that shows issue counts, status distributions, and type breakdowns. All metrics respect the current filter state, so you can drill down into a specific project, scope, or label and see accurate totals for just that slice.",
      "Metrics update in real time when the gossip layer is active. The panel is designed for quick standups and progress checks—see at a glance how many issues are open, in progress, or blocked without running a separate query."
    ],
    href: "/features/agile-metrics"
  }
];
