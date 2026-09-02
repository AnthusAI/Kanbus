import React, { useMemo, useState } from "react";
import { StatusTree } from "@kanbus/ui";
import type { Issue } from "../types/issues";

const RIGHT_NOW_PLACEHOLDER = "(no right-now summary)";
const DEFAULT_STATUS_FEED_LIMIT = 30;

interface CurrentStatusPanelProps {
  issues: Issue[];
  limit?: number;
  defaultTreeExpanded?: boolean;
  onSelectIssue?: (issue: Issue) => void;
  selectedIssueId?: string | null;
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

function resolveRightNowSummary(issue: Issue): string {
  const summary = issue.right_now_summary;
  if (summary == null || summary.trim().length === 0) {
    return RIGHT_NOW_PLACEHOLDER;
  }
  return summary;
}

export function CurrentStatusPanel({
  issues,
  limit = DEFAULT_STATUS_FEED_LIMIT,
  defaultTreeExpanded = false,
  onSelectIssue,
  selectedIssueId = null,
}: CurrentStatusPanelProps) {
  const [treeViewEnabled, setTreeViewEnabled] = useState(false);
  const feedIssues = useMemo(() => {
    const sorted = [...issues].sort(compareRecentlyUpdated);
    if (limit <= 0) {
      return sorted;
    }
    return sorted.slice(0, limit);
  }, [issues, limit]);

  return (
    <div className="status-panel" data-testid="current-status-panel">
      <div className="status-panel-toolbar">
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
      {treeViewEnabled ? (
        <StatusTree
          issues={issues}
          defaultExpanded={defaultTreeExpanded}
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
              const summaryText = resolveRightNowSummary(issue);
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
