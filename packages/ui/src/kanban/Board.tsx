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
        const displayTitle =
          config?.statuses.find((status) => status.key === column)?.name ?? column;
        return (
          <BoardColumn
            key={column}
            title={displayTitle}
            issues={columnIssues}
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
