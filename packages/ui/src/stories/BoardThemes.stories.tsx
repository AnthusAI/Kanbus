import type { Meta, StoryObj } from "@storybook/react";
import { IssueCollection, IssueDetailPanel, KANBUS_THEMES, KanbusThemeScope, type KanbanConfig, type KanbanIssue, type KanbusColorMode, type KanbusThemeId } from "..";
import "../styles/tokens.css";
import "../styles/kanban.css";
import "../styles/themes/index.css";

const config: KanbanConfig = {
  statuses: [
    { key: "draft", name: "Copywriting", category: "Active" },
    { key: "review", name: "Editorial review", category: "Active" },
    { key: "published", name: "Published", category: "Done" }
  ],
  categories: [{ name: "Active" }, { name: "Done" }],
  priorities: { 1: { name: "High" }, 2: { name: "Normal" } },
  type_colors: { article: "blue" },
  workflows: { article: { draft: ["review"], review: ["draft", "published"], published: [] } }
};

const issues: KanbanIssue[] = [
  { id: "article-1", title: "Harbor district plan stalls", type: "article", status: "draft", priority: 1 },
  { id: "article-2", title: "Library hours extended after a petition from residents", type: "article", status: "draft", priority: 2 },
  { id: "article-3", title: "School board seats contested", type: "article", status: "review", priority: 2 },
  { id: "article-4", title: "The agent software factory is throttling up", type: "article", status: "published", priority: 2 },
  { id: "article-5", title: "Skills are procedures, not tools", type: "article", status: "published", priority: 2 }
];

function ThemedBoard({ theme, mode }: { theme: KanbusThemeId; mode: KanbusColorMode }) {
  return (
    <KanbusThemeScope theme={theme} mode={mode} style={{ padding: 16, height: 420, display: "flex", gap: 16 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <IssueCollection issues={issues} config={config} query={{ type: "article" }} motion={{ mode: "static" }} selectedIssueId="article-4" />
      </div>
      <div style={{ width: 280 }}>
        <IssueDetailPanel issue={issues[3]} onClose={() => undefined} fields={[{ label: "Desk", value: "No desk" }]} />
      </div>
    </KanbusThemeScope>
  );
}

const meta: Meta = { title: "Themes/Board themes" };
export default meta;
type Story = StoryObj;

/** All four themes in light and dark mode. */
export const AllThemes: Story = {
  render: () => (
    <div style={{ display: "grid", gap: 24 }}>
      {KANBUS_THEMES.map((theme) =>
        (["light", "dark"] as const).map((mode) => (
          <div key={`${theme.id}-${mode}`}>
            <p style={{ font: "600 13px system-ui", margin: "0 0 6px" }}>{theme.name} ({mode}): {theme.pairing}</p>
            <ThemedBoard theme={theme.id} mode={mode} />
          </div>
        ))
      )}
    </div>
  )
};
