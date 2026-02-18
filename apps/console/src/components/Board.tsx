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
    node.scrollTop = 0;
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
      className="kb-grid gap-2 min-[321px]:px-1 sm:px-2 md:p-3"
    >
      {columns.map((column) => {
        const columnIssues = issues.filter((issue) => issue.status === column);
        return (
          <BoardColumn
            key={column}
            title={column}
            issues={columnIssues}
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
