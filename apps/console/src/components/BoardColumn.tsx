import React from "react";
import type { Issue, ProjectConfig } from "../types/issues";
import { IssueCard } from "./IssueCard";

interface BoardColumnProps {
  title: string;
  issues: Issue[];
  priorityLookup: Record<number, string>;
  config?: ProjectConfig;
  onSelectIssue?: (issue: Issue) => void;
  selectedIssueId?: string | null;
}

function BoardColumnComponent({
  title,
  issues,
  priorityLookup,
  config,
  onSelectIssue,
  selectedIssueId
}: BoardColumnProps) {
  return (
    <div className="kb-column flex flex-col h-full min-h-0">
      <div className="kb-column-header h-7 items-center flex justify-between px-3">
        <span>{title.replace(/_/g, " ")}</span>
        <span className="pr-3">{issues.length}</span>
      </div>
      <div className="kb-column-scroll mt-1 flex-1 min-h-0 overflow-y-auto">
        <div className="grid gap-2">
          {issues.map((issue) => (
            <IssueCard
              key={issue.id}
              issue={issue}
              priorityName={priorityLookup[issue.priority] ?? "medium"}
              config={config}
              onSelect={onSelectIssue}
              isSelected={selectedIssueId === issue.id}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export const BoardColumn = React.memo(BoardColumnComponent);
