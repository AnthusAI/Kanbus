import React, { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import type { KanbanConfig, KanbanIssue } from "./types";
import { BoardColumn } from "./BoardColumn";
import { useBoardTransitions } from "./useBoardTransitions";
import {
  normalizeMotionConfig,
  type KanbanMotionConfig
} from "./motion";

interface BoardProps {
  columns: string[];
  issues: KanbanIssue[];
  priorityLookup: Record<number, string>;
  config?: KanbanConfig;
  onSelectIssue?: (issue: KanbanIssue) => void;
  selectedIssueId?: string | null;
  transitionKey?: string;
  detailOpen?: boolean;
  collapsedColumns?: Set<string>;
  onToggleCollapse?: (column: string) => void;
  motion?: KanbanMotionConfig;
}

function parseIssueTimestamp(issue: KanbanIssue): number {
  const parsed = Date.parse(issue.updated_at ?? "");
  return Number.isNaN(parsed) ? Number.NEGATIVE_INFINITY : parsed;
}

function compareRecentFirst(a: KanbanIssue, b: KanbanIssue): number {
  const aTimestamp = parseIssueTimestamp(a);
  const bTimestamp = parseIssueTimestamp(b);
  if (aTimestamp < bTimestamp) return 1;
  if (aTimestamp > bTimestamp) return -1;
  if (a.id < b.id) return -1;
  if (a.id > b.id) return 1;
  return 0;
}

function isDoneColumn(column: string, config?: KanbanConfig): boolean {
  const doneNames = new Set(["done", "closed", "complete", "completed", "resolved"]);
  const status = config?.statuses.find((item) => item.key === column);
  if (status?.category) {
    const normalizedCategory = status.category.trim().toLowerCase();
    if (doneNames.has(normalizedCategory)) {
      return true;
    }
  }
  return doneNames.has(column.trim().toLowerCase());
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
  onToggleCollapse,
  motion
}: BoardProps) {
  const useIsomorphicLayoutEffect =
    typeof window === "undefined" ? useEffect : useLayoutEffect;
  const resolvedMotion = normalizeMotionConfig(motion);
  const scope = useBoardTransitions(transitionKey ?? "", resolvedMotion.mode === "css");
  const boardRef = useRef<HTMLDivElement | null>(null);
  const didInitialScroll = useRef(false);

  const setBoardRef = useCallback(
    (node: HTMLDivElement | null) => {
      scope.current = node;
      boardRef.current = node;
    },
    [scope]
  );

  useIsomorphicLayoutEffect(() => {
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
    <div ref={setBoardRef} className="kb-grid gap-2">
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
            motion={resolvedMotion}
          />
        );
      })}
    </div>
  );
}

export const Board = React.memo(BoardComponent);
