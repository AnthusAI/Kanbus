import React, { useMemo, type ReactNode } from "react";
import { Board } from "./Board";
import { IssueCard } from "./IssueCard";
import { filterIssues, type IssueQuery } from "./issue-query";
import { getStatusColumnsForIssueTypes } from "./workflow-columns";
import type { KanbanConfig, KanbanIssue } from "./types";
import type { KanbanMotionConfig } from "./motion";

/** A host-controlled collection with no transport, authentication, or routing. */
export interface IssueCollectionProps<Issue extends KanbanIssue = KanbanIssue> {
  issues: readonly Issue[];
  config: KanbanConfig;
  query?: IssueQuery;
  view?: "board" | "list";
  onSelectIssue?: (issue: Issue) => void;
  selectedIssueId?: string | null;
  collapsedColumns?: Set<string>;
  onToggleCollapse?: (column: string) => void;
  motion?: KanbanMotionConfig;
  emptyMessage?: ReactNode;
  ariaLabel?: string;
  className?: string;
}

const EMPTY_QUERY: IssueQuery = {};

/** Compose the existing Kanbus board or cards around a general issue query. */
export function IssueCollection<Issue extends KanbanIssue>({
  issues,
  config,
  query = EMPTY_QUERY,
  view = "board",
  onSelectIssue,
  selectedIssueId,
  collapsedColumns,
  onToggleCollapse,
  motion,
  emptyMessage = "No matching issues",
  ariaLabel = "Issues",
  className
}: IssueCollectionProps<Issue>) {
  const visibleIssues = useMemo(() => filterIssues(issues, query), [issues, query]);
  const columns = useMemo(() => getStatusColumnsForIssueTypes(config, query.type === undefined ? [] : [query.type])
    .filter((status) => query.status === undefined || status === query.status), [config, query.type, query.status]);
  const priorityLookup = useMemo(() => Object.fromEntries(
    Object.entries(config.priorities).map(([priority, definition]) => [priority, definition.name])
  ), [config.priorities]);

  const selectIssue = (issue: KanbanIssue) => {
    const original = visibleIssues.find((candidate) => candidate === issue);
    if (original) onSelectIssue?.(original);
  };

  return (
    <section className={`kb-issue-collection ${className ?? ""}`} aria-label={ariaLabel}>
      {visibleIssues.length === 0 ? <p role="status">{emptyMessage}</p> : null}
      {view === "board" ? (
        <Board
          columns={columns}
          issues={visibleIssues}
          priorityLookup={priorityLookup}
          config={config}
          onSelectIssue={selectIssue}
          selectedIssueId={selectedIssueId}
          collapsedColumns={collapsedColumns}
          onToggleCollapse={onToggleCollapse}
          transitionKey={JSON.stringify(query)}
          motion={motion}
        />
      ) : (
        <ul className="kb-issue-list">
          {visibleIssues.map((issue, index) => (
            <li key={issue.id}>
              <IssueCard
                issue={issue}
                priorityName={priorityLookup[issue.priority] ?? String(issue.priority)}
                config={config}
                onSelect={selectIssue}
                isSelected={issue.id === selectedIssueId}
                motion={motion}
                motionIndex={index}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
