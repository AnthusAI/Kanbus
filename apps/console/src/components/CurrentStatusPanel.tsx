import React, { useMemo, useState } from "react";
import {
  StatusTree,
  resolveRightNowSummaryText,
  type RightNowSummaryDisplayMode
} from "@kanbus/ui";
import type { Issue, StatusDefinition } from "../types/issues";

const DEFAULT_STATUS_FEED_LIMIT = 30;
const DEFAULT_NOW_STATUS_FILTER = "in_progress";
const NOW_STATUS_FILTER_ALL = "all";

interface CurrentStatusPanelProps {
  issues: Issue[];
  statuses?: StatusDefinition[];
  boardTitle?: string;
  limit?: number;
  defaultTreeExpanded?: boolean;
  onSelectIssue?: (issue: Issue) => void;
  selectedIssueId?: string | null;
  rightNowSummaryDisplayMode?: RightNowSummaryDisplayMode;
}

function parseTimestamp(value: string | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function compareRecentlyUpdated(left: Issue, right: Issue): number {
  const leftTimestamp = parseTimestamp(left.updated_at);
  const rightTimestamp = parseTimestamp(right.updated_at);
  const hasLeft = leftTimestamp != null;
  const hasRight = rightTimestamp != null;
  if (hasLeft && !hasRight) {
    return -1;
  }
  if (!hasLeft && hasRight) {
    return 1;
  }
  if (!hasLeft && !hasRight) {
    return left.id.localeCompare(right.id);
  }
  const order = (leftTimestamp ?? 0) - (rightTimestamp ?? 0);
  if (order === 0) {
    return left.id.localeCompare(right.id);
  }
  return -order;
}

function formatUpdatedAt(value: string | undefined): string {
  if (!value) {
    return "";
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return new Date(parsed).toISOString().replace(".000Z", "Z");
}

function collectNowTreeIssues(allIssues: Issue[], matchingIssues: Issue[]): Issue[] {
  if (matchingIssues.length === 0 || matchingIssues.length === allIssues.length) {
    return matchingIssues;
  }
  const childrenByParent = new Map<string, Issue[]>();
  for (const issue of allIssues) {
    if (!issue.parent) {
      continue;
    }
    const siblings = childrenByParent.get(issue.parent) ?? [];
    siblings.push(issue);
    childrenByParent.set(issue.parent, siblings);
  }
  const included = new Set<string>();
  const pending = matchingIssues.map((issue) => issue.id);
  while (pending.length > 0) {
    const identifier = pending.pop();
    if (!identifier || included.has(identifier)) {
      continue;
    }
    included.add(identifier);
    const children = childrenByParent.get(identifier) ?? [];
    for (const child of children) {
      pending.push(child.id);
    }
  }
  return allIssues.filter((issue) => included.has(issue.id));
}

export function CurrentStatusPanel({
  issues,
  statuses = [],
  boardTitle = "",
  limit = DEFAULT_STATUS_FEED_LIMIT,
  defaultTreeExpanded = false,
  onSelectIssue,
  selectedIssueId = null,
  rightNowSummaryDisplayMode = "loading",
}: CurrentStatusPanelProps) {
  const [treeViewEnabled, setTreeViewEnabled] = useState(true);
  const [statusFilter, setStatusFilter] = useState(DEFAULT_NOW_STATUS_FILTER);
  const visibleIssues = useMemo(() => {
    if (statusFilter === NOW_STATUS_FILTER_ALL) {
      return issues;
    }
    return issues.filter((issue) => issue.status === statusFilter);
  }, [issues, statusFilter]);
  const treeIssues = useMemo(
    () => collectNowTreeIssues(issues, visibleIssues),
    [issues, visibleIssues]
  );
  const feedIssues = useMemo(() => {
    const sorted = [...visibleIssues].sort(compareRecentlyUpdated);
    if (limit <= 0) {
      return sorted;
    }
    return sorted.slice(0, limit);
  }, [visibleIssues, limit]);

  return (
    <div className="status-panel" data-testid="current-status-panel">
      <div className="status-panel-toolbar">
        {boardTitle ? (
          <h1 className="status-board-title" data-testid="now-board-title">
            {boardTitle}
          </h1>
        ) : null}
        <div className="status-panel-toolbar-actions">
        <label className="status-status-filter">
          <span>Status</span>
          <select
            data-testid="now-status-filter"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value={NOW_STATUS_FILTER_ALL}>All</option>
            {statuses.map((status) => (
              <option key={status.key} value={status.key}>
                {status.name}
              </option>
            ))}
          </select>
        </label>
        <label className="status-tree-view-toggle">
          <input
            type="checkbox"
            data-testid="status-tree-toggle"
            checked={treeViewEnabled}
            onChange={(event) => setTreeViewEnabled(event.target.checked)}
          />
          <span>Tree</span>
        </label>
        </div>
      </div>
      {treeViewEnabled ? (
        <StatusTree
          issues={treeIssues}
          defaultExpanded={defaultTreeExpanded}
          rightNowSummaryDisplayMode={rightNowSummaryDisplayMode}
          onSelectIssue={
            onSelectIssue
              ? (treeIssue) => {
                  const issue = issues.find((candidate) => candidate.id === treeIssue.id);
                  if (issue) {
                    onSelectIssue(issue);
                  }
                }
              : undefined
          }
          selectedIssueId={selectedIssueId}
        />
      ) : (
        <div className="status-feed" data-testid="status-feed">
          {feedIssues.length === 0 ? (
            <div className="status-feed-empty" data-testid="status-feed-empty">
              No issues to show
            </div>
          ) : (
            feedIssues.map((issue) => {
              const isSelected = selectedIssueId === issue.id;
              const summaryText = resolveRightNowSummaryText(
                issue.right_now_summary,
                rightNowSummaryDisplayMode
              );
              return (
                <button
                  key={issue.id}
                  type="button"
                  className={`status-feed-row${isSelected ? " status-feed-row-selected" : ""}`}
                  data-testid="status-feed-row"
                  data-issue-title={issue.title}
                  data-issue-id={issue.id}
                  onClick={() => onSelectIssue?.(issue)}
                >
                  <div className="status-feed-header">
                    <span className="status-feed-timestamp" data-testid="status-feed-timestamp">
                      {formatUpdatedAt(issue.updated_at)}
                    </span>
                    <span className="status-feed-id" data-testid="status-feed-id">
                      {issue.id}
                    </span>
                    <span
                      className="status-feed-title"
                      data-testid="status-feed-title"
                    >
                      {issue.title}
                    </span>
                  </div>
                  <div
                    className="status-feed-summary"
                    data-testid="status-feed-summary"
                  >
                    {summaryText}
                  </div>
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
