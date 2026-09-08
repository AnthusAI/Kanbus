import React, { useCallback, useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { formatIssueId } from "./format-issue-id";
import { getTypeIcon } from "./issue-icons";
import {
  buildIssueColorStyle,
  buildStatusBadgeStyle,
  resolveIssueAccentColorName,
  resolveStatusBadgeColorName
} from "./issue-colors";
import type { KanbanConfig, KanbanIssue } from "./types";
import { resolveRightNowSummaryText, type RightNowSummaryDisplayMode } from "./right-now-summary-display";


export interface StatusTreeIssue {
  id: string;
  title: string;
  type?: string;
  status?: string;
  priority?: number;
  parent?: string;
  updated_at?: string;
  right_now_summary?: string | null;
}

interface StatusTreeNode {
  issue: StatusTreeIssue;
  children: StatusTreeNode[];
}

interface StatusTreeProps {
  issues: StatusTreeIssue[];
  config?: KanbanConfig;
  priorityLookup?: Record<number, string>;
  defaultExpanded: boolean;
  onSelectIssue?: (issue: StatusTreeIssue) => void;
  selectedIssueId?: string | null;
  rightNowSummaryDisplayMode: RightNowSummaryDisplayMode;
}

function parseTimestamp(value: string | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function compareRecentlyUpdated(left: StatusTreeIssue, right: StatusTreeIssue): number {
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


function toKanbanIssue(issue: StatusTreeIssue): KanbanIssue {
  return {
    id: issue.id,
    title: issue.title,
    type: issue.type ?? "task",
    status: issue.status ?? "open",
    priority: issue.priority ?? 2
  };
}

function getTreeLatestUpdate(node: StatusTreeNode): number {
  let max = parseTimestamp(node.issue.updated_at) ?? 0;
  for (const child of node.children) {
    const childMax = getTreeLatestUpdate(child);
    if (childMax > max) {
      max = childMax;
    }
  }
  return max;
}

function compareNodesRecentlyUpdated(left: StatusTreeNode, right: StatusTreeNode): number {
  const leftMax = getTreeLatestUpdate(left);
  const rightMax = getTreeLatestUpdate(right);
  if (leftMax !== rightMax) {
    return rightMax - leftMax;
  }
  return left.issue.id.localeCompare(right.issue.id);
}

function buildStatusTree(issues: StatusTreeIssue[]): StatusTreeNode[] {
  const identifiers = new Set(issues.map((issue) => issue.id));
  const childrenByParent = new Map<string, StatusTreeIssue[]>();

  for (const issue of issues) {
    if (!issue.parent) {
      continue;
    }
    const siblings = childrenByParent.get(issue.parent) ?? [];
    siblings.push(issue);
    childrenByParent.set(issue.parent, siblings);
  }

  const buildNode = (issue: StatusTreeIssue): StatusTreeNode => {
    const children = (childrenByParent.get(issue.id) ?? []).map(buildNode);
    children.sort(compareNodesRecentlyUpdated);
    return { issue, children };
  };

  const roots = issues
    .filter((issue) => !issue.parent || !identifiers.has(issue.parent))
    .map(buildNode);
  
  roots.sort(compareNodesRecentlyUpdated);

  return roots;
}

interface StatusTreeRowProps {
  node: StatusTreeNode;
  depth: number;
  defaultExpanded: boolean;
  expandedOverrides: Record<string, boolean>;
  onToggleExpanded: (issueId: string, expanded: boolean) => void;
  onSelectIssue?: (issue: StatusTreeIssue) => void;
  selectedIssueId?: string | null;
  rightNowSummaryDisplayMode: RightNowSummaryDisplayMode;
  config?: KanbanConfig;
  priorityLookup: Record<number, string>;
}

function StatusTreeRow({
  node,
  depth,
  defaultExpanded,
  expandedOverrides,
  onToggleExpanded,
  onSelectIssue,
  selectedIssueId = null,
  rightNowSummaryDisplayMode,
  config,
  priorityLookup
}: StatusTreeRowProps) {
  const { issue, children } = node;
  const hasChildren = children.length > 0;
  const expanded = expandedOverrides[issue.id] ?? defaultExpanded;
  const summaryText = resolveRightNowSummaryText(issue.right_now_summary, rightNowSummaryDisplayMode);
  const isSelected = selectedIssueId === issue.id;
  const kanbanIssue = toKanbanIssue(issue);
  const IssueTypeIcon = getTypeIcon(kanbanIssue.type, kanbanIssue.status);
  const ExpandIcon = expanded ? ChevronDown : ChevronRight;
  const statusKey = kanbanIssue.status;
  const statusLabel =
    config?.statuses.find((status) => status.key === statusKey)?.name ?? statusKey;
  const priorityName = priorityLookup[kanbanIssue.priority] ?? "medium";
  const issueStyle = config ? buildIssueColorStyle(config, kanbanIssue) : undefined;
  const statusBadgeStyle =
    config && statusKey ? buildStatusBadgeStyle(config, statusKey) : undefined;
  const accentColorName = config
    ? resolveIssueAccentColorName(config, kanbanIssue)
    : null;
  const statusColorName =
    config && statusKey ? resolveStatusBadgeColorName(config, statusKey) : null;
  const formattedIssueId = formatIssueId(issue.id);

  const handleToggle = useCallback(
    (event: React.MouseEvent<HTMLButtonElement>) => {
      event.stopPropagation();
      onToggleExpanded(issue.id, !expanded);
    },
    [expanded, issue.id, onToggleExpanded]
  );

  return (
    <>
      <div
        className="status-tree-entry"
        style={{ paddingLeft: `${depth * 1.25}rem` }}
        data-tree-depth={depth}
      >
        <div
          className={`status-tree-row${isSelected ? " status-tree-row-selected" : ""}`}
          style={issueStyle}
          data-testid="status-tree-row"
          data-issue-title={issue.title}
          data-issue-id={issue.id}
          data-issue-type={kanbanIssue.type}
          data-issue-status={statusKey || undefined}
          data-priority={priorityName}
          data-accent-color={accentColorName ?? undefined}
          data-tree-expanded={hasChildren ? String(expanded) : undefined}
        >
          <div className="status-tree-accent-stripe" aria-hidden="true" />
          <div className="status-tree-content">
            <div className="status-tree-meta-row">
              {hasChildren ? (
                <button
                  type="button"
                  className="status-tree-toggle"
                  data-testid="status-tree-node-toggle"
                  data-issue-title={issue.title}
                  aria-expanded={expanded}
                  aria-label={expanded ? "Collapse descendants" : "Expand descendants"}
                  onClick={handleToggle}
                >
                  <ExpandIcon className="status-tree-toggle-icon" aria-hidden="true" />
                </button>
              ) : null}
              <div className="status-tree-accent-bar">
                <div className="status-tree-accent-left">
                  <IssueTypeIcon className="issue-accent-icon status-tree-type-icon" aria-hidden="true" />
                  <span className="issue-accent-id status-tree-id" data-testid="status-tree-id">
                    {formattedIssueId}
                  </span>
                </div>
                <div className="issue-accent-priority status-tree-priority">{priorityName}</div>
              </div>
            </div>
            <div className="status-tree-title-row">
              <button
                type="button"
                className={`status-tree-title-button${isSelected ? " status-tree-title-button-selected" : ""}`}
                data-testid="status-tree-title"
                onClick={() => onSelectIssue?.(issue)}
              >
                {issue.title}
              </button>
              {statusKey ? (
                <span
                  className="status-badge status-tree-status"
                  data-testid="status-tree-status"
                  data-issue-status={statusKey}
                  data-status-color={statusColorName ?? undefined}
                  style={statusBadgeStyle}
                >
                  {statusLabel}
                </span>
              ) : null}
            </div>
            <div className="status-tree-summary" data-testid="status-tree-summary">
              {summaryText}
            </div>
          </div>
        </div>
      </div>
      {hasChildren && expanded
        ? children.map((child) => (
            <StatusTreeRow
              key={child.issue.id}
              node={child}
              depth={depth + 1}
              defaultExpanded={defaultExpanded}
              expandedOverrides={expandedOverrides}
              onToggleExpanded={onToggleExpanded}
              onSelectIssue={onSelectIssue}
              selectedIssueId={selectedIssueId}
              rightNowSummaryDisplayMode={rightNowSummaryDisplayMode}
              config={config}
              priorityLookup={priorityLookup}
            />
          ))
        : null}
    </>
  );
}

export function StatusTree({
  issues,
  config,
  priorityLookup = {},
  defaultExpanded,
  onSelectIssue,
  selectedIssueId = null,
  rightNowSummaryDisplayMode = "placeholder"
}: StatusTreeProps) {
  const [expandedOverrides, setExpandedOverrides] = useState<Record<string, boolean>>({});
  const roots = useMemo(() => buildStatusTree(issues), [issues]);

  const handleToggleExpanded = useCallback((issueId: string, expanded: boolean) => {
    setExpandedOverrides((previous) => ({
      ...previous,
      [issueId]: expanded
    }));
  }, []);

  if (roots.length === 0) {
    return (
      <div className="status-tree-empty" data-testid="status-tree-empty">
        No issues to show
      </div>
    );
  }

  return (
    <div className="status-tree" data-testid="status-tree">
      {roots.map((node) => (
        <StatusTreeRow
          key={node.issue.id}
          node={node}
          depth={0}
          defaultExpanded={defaultExpanded}
          expandedOverrides={expandedOverrides}
          onToggleExpanded={handleToggleExpanded}
          onSelectIssue={onSelectIssue}
          selectedIssueId={selectedIssueId}
          rightNowSummaryDisplayMode={rightNowSummaryDisplayMode}
          config={config}
          priorityLookup={priorityLookup}
        />
      ))}
    </div>
  );
}
