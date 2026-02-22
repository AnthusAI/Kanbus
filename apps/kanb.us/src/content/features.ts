export type FeatureEntry = {
  title: string;
  description: string;
  href: string;
  eyebrow?: string;
};

export const FEATURE_ENTRIES: FeatureEntry[] = [
  {
    title: "Jira Sync",
    description: "Pull Jira issues into your repository so agents always have the full context.",
    href: "/features/jira-sync"
  },
  {
    title: "Local Tasks",
    description: "Keep private tasks off git and promote them when they are ready to share.",
    href: "/features/local-tasks"
  }
];
