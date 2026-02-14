import React from "react";
import {
  Bug,
  BookOpen,
  CheckSquare,
  ListChecks,
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
  isSelected?: boolean;
}

export function IssueCard({
  issue,
  priorityName,
  onSelect,
  isSelected
}: IssueCardProps) {
  const handleClick = () => {
    if (onSelect) {
      onSelect(issue);
    }
  };

  const IssueTypeIcon =
    {
      initiative: Rocket,
      epic: ListChecks,
      task: CheckSquare,
      "sub-task": CornerDownRight,
      bug: Bug,
      story: BookOpen,
      chore: Wrench
    }[issue.type] ?? Tag;

  return (
    <div
      className={`issue-card rounded-xl bg-card p-3 grid cursor-pointer overflow-hidden relative hover:bg-card-muted ${isSelected ? " issue-card-selected" : ""}`}
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
      <div className="issue-accent-bar -m-3 mb-0 h-7 w-[calc(100%+1.5rem)] px-3 flex items-center">
        <div className="issue-accent-row gap-2 w-full flex items-center justify-between">
          <div className="issue-accent-left gap-1 inline-flex items-center min-w-0">
            <IssueTypeIcon className="issue-accent-icon" />
            <span className="issue-accent-id">{issue.id}</span>
          </div>
          <div className="issue-accent-priority">{priorityName}</div>
        </div>
      </div>
      <div className="grid gap-1 pt-2">
        <div className="flex items-center justify-between text-xs text-muted">
          {issue.assignee ? <span>{issue.assignee}</span> : <span />}
        </div>
        <h3 className="text-base font-semibold text-foreground">{issue.title}</h3>
        <div className="flex flex-wrap" />
      </div>
    </div>
  );
}
