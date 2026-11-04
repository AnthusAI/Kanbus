import React, { useState } from "react";
import * as Kanbus from "@kanbus/ui";
import type { HostIssue } from "./fixture-data";

export type StackedDataset = "articles" | "sections" | "large" | "long";

export interface StackedBoardSettings {
  component?: "collection" | "board";
  layout?: Kanbus.BoardLayout;
  stackedBelowWidth?: number;
  dataset?: StackedDataset;
  motionMode?: "static" | "css";
  columnStateKey?: string;
  collapsePublishedByConfiguration?: boolean;
  theme?: Kanbus.KanbusThemeId;
  mode?: Kanbus.KanbusColorMode;
  collapsedStatusKey?: string;
  initialSelectedIssueId?: string;
  columnNearEndThreshold?: number;
  searchText?: string;
}

export const stackedStatuses = ["draft", "review", "published"];

export function buildStackedIssues(dataset: StackedDataset, articleSource: HostIssue[]): HostIssue[] {
  if (dataset === "articles") return articleSource.filter((issue) => issue.type === "article").map((issue) => ({ ...issue }));
  const baseTime = Date.UTC(2026, 0, 1);
  if (dataset === "large") {
    return Array.from({ length: 500 }, (_, index) => ({
      id: `bulk-${index + 1}`, title: `Bulk issue ${index + 1}`, type: "article", status: "draft", priority: 2,
      created_at: new Date(baseTime + index * 60_000).toISOString()
    }));
  }
  if (dataset === "long") {
    const longUnbrokenWord = "Unbreakable".repeat(14);
    return stackedStatuses.flatMap((status) => Array.from({ length: 10 }, (_, index) => ({
      id: index === 0 && status === "draft" ? `host-${"identifier".repeat(9)}` : index === 1 && status === "draft" ? "news/three-sources-confirm-the-zoning-reversal" : `${status}-${index + 1}`,
      title: index === 0 && status === "draft" ? longUnbrokenWord : `${status} headline number ${index + 1} that runs long enough to wrap onto a second line`,
      type: "article", status, priority: index % 2 === 0 ? 1 : 2,
      created_at: new Date(baseTime + index * 60_000).toISOString()
    })));
  }
  return stackedStatuses.flatMap((status, statusIndex) => Array.from({ length: 60 }, (_, index) => ({
    id: `${status}-${index + 1}`, title: `${status} issue ${index + 1}`, type: "article", status, priority: 2,
    created_at: new Date(baseTime + (statusIndex * 60 + index) * 60_000).toISOString()
  })));
}

export function StackedBoardHost({ settings, records, baseConfiguration }: { settings: StackedBoardSettings; records: HostIssue[]; baseConfiguration: Kanbus.KanbanConfig }) {
  const [selected, setSelected] = useState<Kanbus.KanbanIssue | null>(
    () => records.find((issue) => issue.id === settings.initialSelectedIssueId) ?? null
  );
  const stackedConfiguration = {
    ...baseConfiguration,
    statuses: baseConfiguration.statuses.map((status) => ({
      ...status,
      collapsed: (settings.collapsePublishedByConfiguration === true && status.key === "published")
        || status.key === settings.collapsedStatusKey
    }))
  };
  const common = {
    config: stackedConfiguration,
    onSelectIssue: setSelected,
    selectedIssueId: selected?.id,
    detailOpen: selected !== null,
    motion: { mode: settings.motionMode ?? "static" } as const,
    layout: settings.layout,
    formatIssueId: settings.dataset === "long" ? (issue: Kanbus.KanbanIssue) => issue.id : undefined,
    stackedBelowWidth: settings.stackedBelowWidth,
    columnStateKey: settings.columnStateKey,
    columnNearEndThreshold: settings.columnNearEndThreshold,
    onColumnNearEnd: (columnKey: string) => { window.nearEndCalls.push(columnKey); }
  };
  const boardContent = <div className={settings.theme ? undefined : "kb-theme-organizer"}>
    <div className="fixture-stacked-host" style={{ height: settings.theme ? "100vh" : 600 }}>
      {settings.component === "board"
        ? <Kanbus.Board {...common} columns={stackedStatuses} issues={records}
            priorityLookup={{ 1: "High", 2: "Normal" }} />
        : <Kanbus.IssueCollection {...common} issues={records} query={{ type: "article", ...(settings.searchText ? { search: settings.searchText } : {}) }} />}
    </div>
    {selected && <Kanbus.IssueDetailPanel issue={selected} onClose={() => setSelected(null)} />}
  </div>;
  if (settings.theme) {
    return <Kanbus.KanbusThemeScope theme={settings.theme} mode={settings.mode}>{boardContent}</Kanbus.KanbusThemeScope>;
  }
  return boardContent;
}

