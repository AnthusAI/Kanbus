import React from "react";
import type { Issue } from "../types/issues";
import { IssueCard } from "./IssueCard";

interface BoardColumnProps {
  title: string;
  issues: Issue[];
  priorityLookup: Record<number, string>;
  onSelectIssue?: (issue: Issue) => void;
}

export function BoardColumn({
  title,
  issues,
  priorityLookup,
  onSelectIssue
}: BoardColumnProps) {
  return (
    <div className="kb-column">
      <div className="kb-column-header">
        <span>{title.replace(/_/g, " ")}</span>
        <span>{issues.length}</span>
      </div>
      <div className="grid gap-3">
        {issues.map((issue) => (
          <IssueCard
            key={issue.id}
            issue={issue}
            priorityName={priorityLookup[issue.priority] ?? "medium"}
            onSelect={onSelectIssue}
          />
        ))}
      </div>
    </div>
  );
}
