import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import * as Kanbus from "@kanbus/ui";
import "@kanbus/ui/styles/tokens.css";
import "@kanbus/ui/styles/kanban.css";
import "@kanbus/ui/styles/organizer.css";
import "@kanbus/ui/styles/themes/index.css";
import "./host-utilities.css";

interface HostIssue extends Kanbus.KanbanIssue {
  hostOnlyField?: string;
}

declare global {
  interface Window {
    renderCollection: (query?: Kanbus.IssueQuery, view?: "board" | "list") => void;
    filterArticles: (query: Kanbus.IssueQuery) => string[];
    updateIssue: (identifier: string, status: string) => void;
    renderStandalone: () => void;
    renderTypeFilter: (mode: "light" | "dark") => void;
    renderUnselectedTypeFilter: () => void;
    renderBoardConsumer: (kind: "console" | "embedded", key: string) => void;
    selectedIssue?: HostIssue;
    selectedOriginal?: boolean;
    hostReady: boolean;
    renderTheme: (theme: Kanbus.KanbusThemeId, mode?: Kanbus.KanbusColorMode, tokens?: Record<`--kb-theme-${string}`, string>, selectedId?: string) => void;
    kanbusThemeIds: string[];
    kanbusThemeFonts: Record<string, string>;
    renderHostIssueIds: (theme: Kanbus.KanbusThemeId, withHostFormatter: boolean) => void;
    renderOrganizer: (mode?: "light" | "dark", initialScroll?: "start" | "end" | "preserve") => void;
    renderLargeColumn: (issueCount: number) => void;
    replaceLargeColumnWithCopies: (retitledIdentifier: string, newTitle: string) => void;
    resetCardRenderCounts: () => void;
    cardRenderCounts: () => Record<string, number>;
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
    excerpt: "The council met on Tuesday evening to debate the long awaited proposal for the harbor district, hearing from residents, merchants and engineers before adjourning without a vote until the following week.",
    assignee: "alex", labels: ["newsletter"], parent: "series-1", custom: { score: 8, ready: true },
    comments: [{ author: "alex", created_at: "2026-10-14T00:00:00Z", text: "Hidden text", comment_type: "summary", data: { activity_summary: "Arrange the interview" } }] },
  { id: "article-2", title: "Second article", type: "article", status: "review", priority: 2,
    assignee: "ben", custom: { score: "8" } },
  { id: "article-3", title: "Third article", type: "article", status: "draft", priority: 2,
    assignee: "alex", custom: { score: 12 } },
  { id: "task-1", title: "Other work", type: "task", status: "open", priority: 2 }
];

const root = createRoot(document.getElementById("root")!);
let largeColumnIssues: HostIssue[] = [];
let largeColumnSelectedIdentifier: string | null = null;
const renderCountByIssueIdentifier = new Map<string, number>();
const countingIssueIdFormatter: Kanbus.IssueIdFormatter = (issue) => {
  renderCountByIssueIdentifier.set(issue.id, (renderCountByIssueIdentifier.get(issue.id) ?? 0) + 1);
  return issue.id;
};

function selectLargeColumnIssue(issue: Kanbus.KanbanIssue) {
  largeColumnSelectedIdentifier = issue.id;
  renderLargeColumnBoard();
}

function renderLargeColumnBoard() {
  root.render(
    <div className="fixture-large-column" style={{ height: 700 }}>
      <Kanbus.Board
        columns={["open"]}
        issues={largeColumnIssues}
        priorityLookup={{ 1: "High", 2: "Normal" }}
        config={configuration}
        motion={{ mode: "static" }}
        formatIssueId={countingIssueIdFormatter}
        selectedIssueId={largeColumnSelectedIdentifier}
        onSelectIssue={selectLargeColumnIssue}
      />
    </div>
  );
}
let currentQuery: Kanbus.IssueQuery = {};
let organizer = false;
let organizerMode: "light" | "dark" = "light";
let organizerScroll: "start" | "end" | "preserve" = "start";
let currentView: "board" | "list" = "board";

Object.assign(window, {
  renderLargeColumn(issueCount: number) {
    largeColumnSelectedIdentifier = null;
    largeColumnIssues = Array.from({ length: issueCount }, (_, index) => ({
      id: `bulk-${index + 1}`,
      title: `Bulk issue ${index + 1}`,
      type: "task",
      status: "open",
      priority: 2,
      created_at: new Date(Date.UTC(2026, 0, 1) + index * 60_000).toISOString()
    }));
    renderLargeColumnBoard();
  },
  replaceLargeColumnWithCopies(retitledIdentifier: string, newTitle: string) {
    largeColumnIssues = largeColumnIssues.map((issue) =>
      issue.id === retitledIdentifier ? { ...issue, title: newTitle } : { ...issue }
    );
    renderLargeColumnBoard();
  },
  resetCardRenderCounts() { renderCountByIssueIdentifier.clear(); },
  cardRenderCounts() { return Object.fromEntries(renderCountByIssueIdentifier); },
  renderUnselectedTypeFilter() { root.render(<TypeFilterHost mode="light" initialValue={null} />); },
  renderBoardConsumer(kind: "console" | "embedded", key: string) {
    root.render(<BoardConsumer key={`${kind}-${key}`} kind={kind} storageKey={key} />);
  },
  renderTypeFilter(mode: "light" | "dark") {
    root.render(<TypeFilterHost mode={mode} />);
  },
  renderCollection(query: Kanbus.IssueQuery = { type: "article" }, view: "board" | "list" = "board") {
    if (!Kanbus.IssueCollection) throw new Error("IssueCollection is not exported");
    organizer = false;
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
    if (organizer) window.renderOrganizer(organizerMode, organizerScroll);
    else window.renderCollection(currentQuery, currentView);
  },
  renderStandalone() {
    root.render(<Kanbus.Board columns={["open"]} issues={issues.filter((issue) => issue.type === "task")}
      priorityLookup={{ 1: "High", 2: "Normal" }} config={configuration} motion={{ mode: "static" }} />);
  },
  renderOrganizer(mode: "light" | "dark" = "light", initialScroll: "start" | "end" | "preserve" = "start") {
    organizer = true; organizerMode = mode; organizerScroll = initialScroll;
    root.render(<OrganizerHost mode={mode} initialScroll={initialScroll} />);
  },
  renderTheme(theme: Kanbus.KanbusThemeId, mode: Kanbus.KanbusColorMode = "light", tokens?: Record<`--kb-theme-${string}`, string>, selectedId?: string) {
    organizer = false;
    root.render(<ThemeHost theme={theme} mode={mode} tokens={tokens} selectedId={selectedId} />);
  },
  renderHostIssueIds(theme: Kanbus.KanbusThemeId, withHostFormatter: boolean) {
    organizer = false;
    root.render(<HostIssueIdsHost theme={theme} withHostFormatter={withHostFormatter} />);
  },
  kanbusThemeIds: Kanbus.KANBUS_THEMES.map((entry) => entry.id),
  kanbusThemeFonts: Kanbus.KANBUS_THEME_FONTS,
  hostReady: true
});

function ThemeHost({ theme, mode, tokens, selectedId }: { theme: Kanbus.KanbusThemeId; mode: Kanbus.KanbusColorMode; tokens?: Record<`--kb-theme-${string}`, string>; selectedId?: string }) {
  const [selected, setSelected] = useState<HostIssue | null>(issues.find((issue) => issue.id === selectedId) ?? null);
  return <Kanbus.KanbusThemeScope theme={theme} mode={mode} tokens={tokens}>
    <Kanbus.IssueCollection issues={issues} config={configuration} query={{ type: "article" }}
      initialScroll="start" motion={{ mode: "static" }} onSelectIssue={setSelected}
      selectedIssueId={selected?.id} columnStateKey="fixture.theme.columns.v1" />
    {selected && <Kanbus.IssueDetailPanel issue={selected} onClose={() => setSelected(null)}
      fields={[{ label: "Editorial score", value: String(selected.custom?.score) }]} />}
  </Kanbus.KanbusThemeScope>;
}

function BoardConsumer({ kind, storageKey }: { kind: "console" | "embedded"; storageKey: string }) {
  const [selected, setSelected] = useState<Kanbus.KanbanIssue | null>(null);
  const config = { ...configuration, statuses: configuration.statuses.map(status => ({ ...status, collapsed: status.key === "published" })) };
  const state = Kanbus.useBoardColumnState({ config, storageKey: kind === "console" ? storageKey : undefined });
  const common = { config, onSelectIssue: setSelected, selectedIssueId: selected?.id, motion: { mode: "static" as const }, initialScroll: "start" as const };
  return <div className={kind === "embedded" ? "kb-theme-organizer" : undefined} style={{ height: 600 }}>
    {kind === "console" ? <Kanbus.Board {...common} columns={["draft", "review", "published"]}
      issues={issues.filter(issue => issue.type === "article")} priorityLookup={{ 1: "High", 2: "Normal" }}
      collapsedColumns={state.collapsedColumns} onToggleCollapse={state.toggleColumn} />
      : <Kanbus.IssueCollection {...common} issues={issues} query={{ type: "article" }} columnStateKey={storageKey} />}
    {selected && <Kanbus.IssueDetailPanel issue={selected} onClose={() => setSelected(null)} />}
  </div>;
}

function TypeFilterHost({ mode, initialValue = "all" }: { mode: "light" | "dark"; initialValue?: string | null }) {
  const [value, setValue] = useState<string | null>(initialValue);
  const config = { ...configuration, hierarchy: ["initiative", "epic", "task", "sub-task"], types: ["story", "article", "reference", "task"] };
  const records = [
    ...issues,
    { id: "story-1", title: "An editorial story", type: "story", status: "open", priority: 2 },
    { id: "reference-1", title: "A source reference", type: "reference", status: "open", priority: 2 }
  ];
  const type = Kanbus.issueTypeFromFilter(value);
  return <div className="kb-theme-organizer" data-color-mode={mode}>
    <Kanbus.IssueTypeFilter config={config} value={value} onChange={setValue} />
    <Kanbus.IssueCollection issues={records} config={config} query={{ type }} view="list" motion={{ mode: "static" }} />
  </div>;
}

function OrganizerHost({ mode, initialScroll }: { mode: "light" | "dark"; initialScroll: "start" | "end" | "preserve" }) {
  const [selected, setSelected] = useState<HostIssue | null>(null);
  return <div className="kb-theme-organizer" data-color-mode={mode}>
    <Kanbus.IssueCollection issues={issues} config={configuration} query={{ type: "article" }}
      initialScroll={initialScroll} motion={{mode:"static"}} onSelectIssue={setSelected}
      selectedIssueId={selected?.id} columnStateKey="fixture.organizer.columns.v1" />
    {selected && <Kanbus.IssueDetailPanel issue={selected} onClose={() => setSelected(null)}
      fields={[{label:"Editorial score",value:String(selected.custom?.score)}]} />}
  </div>;
}

const hostIssueIdFormatter: Kanbus.IssueIdFormatter = (issue) => `articles/Agent-Software-Factory-${issue.id}`;

const hostDetailTask: Kanbus.TaskDetailIssue = {
  id: "article-1", title: "First article", type: "article", status: "draft", priority: 1
};

const hostDetailDescendant: Kanbus.TaskDetailIssue = {
  id: "article-2", title: "Second article", type: "article", status: "review", priority: 2, parent: "article-1"
};

function HostIssueIdsHost({ theme, withHostFormatter }: { theme: Kanbus.KanbusThemeId; withHostFormatter: boolean }) {
  const formatter = withHostFormatter ? hostIssueIdFormatter : undefined;
  const statusTreeIssues = issues.filter((issue) => issue.type === "article").map((issue) => ({
    id: issue.id, title: issue.title, type: issue.type, status: issue.status, priority: issue.priority
  }));
  return <Kanbus.KanbusThemeScope theme={theme} mode="light">
    <Kanbus.IssueCollection issues={issues} config={configuration} query={{ type: "article" }}
      initialScroll="start" motion={{ mode: "static" }} formatIssueId={formatter}
      columnStateKey="fixture.hostids.columns.v1" />
    <Kanbus.IssueIdFormatProvider formatIssueId={formatter}>
      <Kanbus.StatusTree issues={statusTreeIssues} config={configuration} defaultExpanded />
    </Kanbus.IssueIdFormatProvider>
    <Kanbus.IssueDetailPanel issue={issues[0]} onClose={() => undefined} formatIssueId={formatter} />
    <Kanbus.TaskDetailPanel task={hostDetailTask} allIssues={[hostDetailTask, hostDetailDescendant]}
      columns={["draft", "review", "published"]} priorityLookup={{ 1: "High", 2: "Normal" }}
      apiBase="/fixture-api" isOpen isVisible navDirection="none" widthPercent={50} layout="auto"
      onClose={() => undefined} onToggleMaximize={() => undefined} isMaximized={false}
      onAfterClose={() => undefined} onFocus={() => undefined} focusedIssueId={null}
      formatIssueId={formatter} />
  </Kanbus.KanbusThemeScope>;
}
