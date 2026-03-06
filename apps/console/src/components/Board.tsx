import React, { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import type { Issue, ProjectConfig } from "../types/issues";
import { BoardColumn } from "./BoardColumn";
import { useBoardTransitions } from "../hooks/useBoardTransitions";

interface BoardProps {
  columns: string[];
  issues: Issue[];
  priorityLookup: Record<number, string>;
  config?: ProjectConfig;
  onSelectIssue?: (issue: Issue) => void;
  selectedIssueId?: string | null;
  transitionKey: string;
  detailOpen?: boolean;
  collapsedColumns?: Set<string>;
  onToggleCollapse?: (column: string) => void;
}

function compareRecentFirst(a: Issue, b: Issue): number {
  const aTimestamp = a.updated_at ?? a.created_at ?? "";
  const bTimestamp = b.updated_at ?? b.created_at ?? "";
  if (aTimestamp < bTimestamp) return 1;
  if (aTimestamp > bTimestamp) return -1;
  if (a.id < b.id) return -1;
  if (a.id > b.id) return 1;
  return 0;
}

function isDoneColumn(column: string, config?: ProjectConfig): boolean {
  const status = config?.statuses.find((item) => item.key === column);
  if (!status?.category) {
    return false;
  }
  return status.category.trim().toLowerCase() === "done";
}

function BoardComponent({
  columns,
  issues,
  priorityLookup,
  config,
  onSelectIssue,
  selectedIssueId,
  transitionKey,
  detailOpen,
  collapsedColumns = new Set(),
  onToggleCollapse
}: BoardProps) {
  const scope = useBoardTransitions(transitionKey);
  const boardRef = useRef<HTMLDivElement | null>(null);
  const didInitialScroll = useRef(false);

  const setBoardRef = useCallback(
    (node: HTMLDivElement | null) => {
      scope.current = node;
      boardRef.current = node;
    },
    [scope]
  );

  useLayoutEffect(() => {
    if (didInitialScroll.current) {
      return;
    }
    const node = boardRef.current;
    if (!node) {
      return;
    }
    const maxScrollLeft = node.scrollWidth - node.clientWidth;
    if (maxScrollLeft <= 0) {
      return;
    }
    node.scrollLeft = maxScrollLeft;
    didInitialScroll.current = true;
  }, [columns.length]);

  useEffect(() => {
    if (!detailOpen) return;
    const node = boardRef.current;
    if (!node) return;
    const maxScrollLeft = node.scrollWidth - node.clientWidth;
    if (maxScrollLeft <= 0) return;
    node.scrollTo({ left: maxScrollLeft, behavior: "smooth" });
  }, [detailOpen]);

  return (
    <div
      ref={setBoardRef}
      className="kb-grid gap-2"
    >
      {columns.map((column) => {
        const columnIssues = issues.filter((issue) => issue.status === column);
        const orderedIssues = isDoneColumn(column, config)
          ? [...columnIssues].sort(compareRecentFirst)
          : columnIssues;
        const displayTitle =
          config?.statuses.find((status) => status.key === column)?.name ?? column;
        return (
          <BoardColumn
            key={column}
            title={displayTitle}
            issues={orderedIssues}
            priorityLookup={priorityLookup}
            config={config}
            onSelectIssue={onSelectIssue}
            selectedIssueId={selectedIssueId}
            collapsed={collapsedColumns.has(column)}
            onToggleCollapse={() => onToggleCollapse?.(column)}
          />
        );
      })}
    </div>
  );
}

export const Board = React.memo(BoardComponent);
