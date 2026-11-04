import React, { useState } from "react";
import * as Kanbus from "@kanbus/ui";
import type { HostIssue } from "./fixture-data";

export type StackedDataset = "articles" | "sections" | "large";

export interface StackedBoardSettings {
  component?: "collection" | "board";
  layout?: Kanbus.BoardLayout;
  stackedBelowWidth?: number;
  dataset?: StackedDataset;
  motionMode?: "static" | "css";
  columnStateKey?: string;
  collapsePublishedByConfiguration?: boolean;
  collapsedStatusKey?: string;
  initialSelectedIssueId?: string;
  columnNearEndThreshold?: number;
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
    stackedBelowWidth: settings.stackedBelowWidth,
    columnStateKey: settings.columnStateKey,
    columnNearEndThreshold: settings.columnNearEndThreshold,
    onColumnNearEnd: (columnKey: string) => { window.nearEndCalls.push(columnKey); }
  };
  return <div className="kb-theme-organizer">
    <div className="fixture-stacked-host" style={{ height: 600 }}>
      {settings.component === "board"
        ? <Kanbus.Board {...common} columns={stackedStatuses} issues={records}
            priorityLookup={{ 1: "High", 2: "Normal" }} />
        : <Kanbus.IssueCollection {...common} issues={records} query={{ type: "article" }} />}
    </div>
    {selected && <Kanbus.IssueDetailPanel issue={selected} onClose={() => setSelected(null)} />}
  </div>;
}

