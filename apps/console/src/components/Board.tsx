import React from "react";
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
}

function BoardComponent({
  columns,
  issues,
  priorityLookup,
  config,
  onSelectIssue,
  selectedIssueId,
  transitionKey
}: BoardProps) {
  const scope = useBoardTransitions(transitionKey);

  return (
    <div
      ref={scope}
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
          />
        );
      })}
    </div>
  );
}

export const Board = React.memo(BoardComponent);
