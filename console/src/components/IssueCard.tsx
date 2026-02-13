import React from "react";
import {
  Bug,
  BookOpen,
  CheckSquare,
  Flag,
  Rocket,
  Tag,
  Wrench,
  CornerDownRight
} from "lucide-react";
import type { Issue } from "../types/issues";

interface IssueCardProps {
  issue: Issue;
  priorityName: string;
  onSelect?: (issue: Issue) => void;
}

export function IssueCard({ issue, priorityName, onSelect }: IssueCardProps) {
  const handleClick = () => {
    if (onSelect) {
      onSelect(issue);
    }
  };

  const IssueTypeIcon =
    {
      initiative: Rocket,
      epic: Flag,
      task: CheckSquare,
      "sub-task": CornerDownRight,
      bug: Bug,
      story: BookOpen,
      chore: Wrench
    }[issue.type] ?? Tag;

  return (
    <div
      className="issue-card"
      data-status={issue.status}
      data-type={issue.type}
      data-priority={priorityName}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          handleClick();
        }
      }}
    >
      <div className="issue-accent-bar">
        <div className="issue-accent-row">
          <div className="issue-accent-left">
            <IssueTypeIcon className="issue-accent-icon" />
            <span className="issue-accent-id">{issue.id}</span>
          </div>
          <div className="issue-accent-priority">{priorityName}</div>
        </div>
      </div>
      <div className="flex items-center justify-between text-xs text-muted">
        {issue.assignee ? <span>{issue.assignee}</span> : <span />}
      </div>
      <div>
        <h3 className="text-base font-semibold text-foreground">{issue.title}</h3>
      </div>
      <div className="flex flex-wrap gap-2" />
    </div>
  );
}
