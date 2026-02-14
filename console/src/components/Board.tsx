import React from "react";
import type { Issue } from "../types/issues";
import { BoardColumn } from "./BoardColumn";
import { useBoardTransitions } from "../hooks/useBoardTransitions";

interface BoardProps {
  columns: string[];
  issues: Issue[];
  priorityLookup: Record<number, string>;
  onSelectIssue?: (issue: Issue) => void;
  selectedIssueId?: string | null;
  transitionKey: string;
}

export function Board({
  columns,
  issues,
  priorityLookup,
  onSelectIssue,
  selectedIssueId,
  transitionKey
}: BoardProps) {
  const scope = useBoardTransitions(transitionKey);

  return (
    <div ref={scope} className="kb-grid gap-2">
      {columns.map((column) => {
        const columnIssues = issues.filter((issue) => issue.status === column);
        return (
          <BoardColumn
            key={column}
            title={column}
            issues={columnIssues}
            priorityLookup={priorityLookup}
            onSelectIssue={onSelectIssue}
            selectedIssueId={selectedIssueId}
          />
        );
      })}
    </div>
  );
}
