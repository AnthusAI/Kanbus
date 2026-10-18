import type { Meta, StoryObj } from "@storybook/react";
import { IssueCollection, type KanbanConfig, type KanbanIssue } from "..";
import "../styles/tokens.css";
import "../styles/kanban.css";
import "../styles/newsprint.css";

const config: KanbanConfig = {
  statuses: [
    { key: "draft", name: "Draft", category: "Active" },
    { key: "review", name: "Editorial review", category: "Active" },
    { key: "published", name: "Published", category: "Done" }
  ],
  categories: [{ name: "Active" }, { name: "Done" }],
  priorities: { 1: { name: "High" }, 2: { name: "Normal" } },
  type_colors: { article: "blue" },
  workflows: { article: { draft: ["review"], review: ["draft", "published"], published: [] } }
};

const issues: KanbanIssue[] = [
  {
    id: "article-1",
    title: "Harbor district plan stalls",
    type: "article",
    status: "draft",
    priority: 1,
    excerpt:
      "The council met on Tuesday evening to debate the long awaited proposal for the harbor district, hearing from residents, merchants and engineers before adjourning without a vote until the following week."
  },
  { id: "article-2", title: "Library hours extended", type: "article", status: "draft", priority: 2 },
  { id: "article-3", title: "School board seats contested", type: "article", status: "review", priority: 2 }
];

interface NewsprintStoryArguments {
  mode: "light" | "dark";
}

const meta: Meta<NewsprintStoryArguments> = {
  title: "Themes/Newsprint board",
  args: { mode: "light" },
  argTypes: { mode: { control: "inline-radio", options: ["light", "dark"] } },
  render: ({ mode }) => (
    <div data-kanbus-theme="newsprint" data-color-mode={mode} style={{ background: "var(--np-paper)", padding: 16, height: 480 }}>
      <IssueCollection issues={issues} config={config} query={{ type: "article" }} motion={{ mode: "static" }} />
    </div>
  )
};

export default meta;
type Story = StoryObj<NewsprintStoryArguments>;

export const Light: Story = {};
export const Dark: Story = { args: { mode: "dark" } };
