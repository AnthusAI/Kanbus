import React from "react";
import type { Issue } from "../types/issues";
import { IssueCard } from "./IssueCard";

interface BoardColumnProps {
  title: string;
  issues: Issue[];
  priorityLookup: Record<number, string>;
  onSelectIssue?: (issue: Issue) => void;
  selectedIssueId?: string | null;
}

export function BoardColumn({
  title,
  issues,
  priorityLookup,
  onSelectIssue,
  selectedIssueId
}: BoardColumnProps) {
  return (
    <div className="kb-column flex flex-col h-full min-h-0">
      <div className="kb-column-header h-7 items-center flex justify-between px-3">
        <span>{title.replace(/_/g, " ")}</span>
        <span className="pr-3">{issues.length}</span>
      </div>
      <div className="kb-column-scroll mt-1 flex-1 min-h-0 overflow-y-auto pr-0">
        <div className="grid gap-2">
          {issues.map((issue) => (
            <IssueCard
              key={issue.id}
              issue={issue}
              priorityName={priorityLookup[issue.priority] ?? "medium"}
              onSelect={onSelectIssue}
              isSelected={selectedIssueId === issue.id}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
