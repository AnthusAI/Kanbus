import React, { useCallback, useMemo, useState } from "react";

const RIGHT_NOW_PLACEHOLDER = "(no right-now summary)";

export interface StatusTreeIssue {
  id: string;
  title: string;
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
  defaultExpanded: boolean;
  onSelectIssue?: (issue: StatusTreeIssue) => void;
  selectedIssueId?: string | null;
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

function resolveRightNowSummary(issue: StatusTreeIssue): string {
  const summary = issue.right_now_summary;
  if (summary == null || summary.trim().length === 0) {
    return RIGHT_NOW_PLACEHOLDER;
  }
  return summary;
}

function collapseMarker(expanded: boolean): string {
  return expanded ? "[-]" : "[+]";
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

  for (const [parentId, children] of childrenByParent.entries()) {
    childrenByParent.set(
      parentId,
      [...children].sort(compareRecentlyUpdated)
    );
  }

  const roots = issues
    .filter((issue) => !issue.parent || !identifiers.has(issue.parent))
    .sort(compareRecentlyUpdated);

  const buildNode = (issue: StatusTreeIssue): StatusTreeNode => ({
    issue,
    children: (childrenByParent.get(issue.id) ?? []).map(buildNode)
  });

  return roots.map(buildNode);
}

interface StatusTreeRowProps {
  node: StatusTreeNode;
  depth: number;
  defaultExpanded: boolean;
  expandedOverrides: Record<string, boolean>;
  onToggleExpanded: (issueId: string, expanded: boolean) => void;
  onSelectIssue?: (issue: StatusTreeIssue) => void;
  selectedIssueId?: string | null;
}

function StatusTreeRow({
  node,
  depth,
  defaultExpanded,
  expandedOverrides,
  onToggleExpanded,
  onSelectIssue,
  selectedIssueId = null
}: StatusTreeRowProps) {
  const { issue, children } = node;
  const hasChildren = children.length > 0;
  const expanded = expandedOverrides[issue.id] ?? defaultExpanded;
  const summaryText = resolveRightNowSummary(issue);
  const isSelected = selectedIssueId === issue.id;

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
        className={`status-tree-row${isSelected ? " status-tree-row-selected" : ""}`}
        data-testid="status-tree-row"
        data-issue-title={issue.title}
        data-issue-id={issue.id}
        data-tree-depth={depth}
        data-tree-expanded={hasChildren ? String(expanded) : undefined}
      >
        <div className="status-tree-header" style={{ paddingLeft: `${depth * 1.25}rem` }}>
          {hasChildren ? (
            <button
              type="button"
              className="status-tree-toggle"
              data-testid="status-tree-node-toggle"
              data-issue-title={issue.title}
              aria-expanded={expanded}
              onClick={handleToggle}
            >
              {collapseMarker(expanded)}
            </button>
          ) : (
            <span className="status-tree-toggle-spacer" aria-hidden="true" />
          )}
          <button
            type="button"
            className="status-tree-title-button"
            data-testid="status-tree-title"
            onClick={() => onSelectIssue?.(issue)}
          >
            {issue.title}
          </button>
        </div>
        <div
          className="status-tree-summary"
          data-testid="status-tree-summary"
          style={{ paddingLeft: `${depth * 1.25 + 1.75}rem` }}
        >
          {summaryText}
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
            />
          ))
        : null}
    </>
  );
}

export function StatusTree({
  issues,
  defaultExpanded,
  onSelectIssue,
  selectedIssueId = null
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
        />
      ))}
    </div>
  );
}
