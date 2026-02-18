import React, { useLayoutEffect, useRef } from "react";
import {
  Bug,
  BookOpen,
  CheckSquare,
  ListChecks,
  Rocket,
  Square,
  Tag,
  Wrench,
  CornerDownRight
} from "lucide-react";
import type { Issue, ProjectConfig } from "../types/issues";
import { buildIssueColorStyle } from "../utils/issue-colors";
import { formatIssueId } from "../utils/format-issue-id";

interface IssueCardProps {
  issue: Issue;
  priorityName: string;
  config?: ProjectConfig;
  onSelect?: (issue: Issue) => void;
  isSelected?: boolean;
}

function IssueCardComponent({
  issue,
  priorityName,
  config,
  onSelect,
  isSelected
}: IssueCardProps) {
  const cardRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (cardRef.current) {
      cardRef.current.classList.add("issue-animate-seed");
    }
  }, []);

  const handleClick = () => {
    if (onSelect) {
      onSelect(issue);
    }
  };

  const taskIcon = issue.status === "closed" ? CheckSquare : Square;
  const IssueTypeIcon =
    {
      initiative: Rocket,
      epic: ListChecks,
      task: taskIcon,
      "sub-task": CornerDownRight,
      bug: Bug,
      story: BookOpen,
      chore: Wrench
    }[issue.type] ?? Tag;
  const issueStyle = config ? buildIssueColorStyle(config, issue) : undefined;

  return (
    <div
      ref={cardRef}
      className={`issue-card rounded-xl bg-card p-3 grid cursor-pointer overflow-hidden relative hover:bg-card-muted transition-shadow duration-300 ${isSelected ? " ring-inset ring-[6px] ring-[var(--text-muted)]" : ""}`}
      style={issueStyle}
      data-status={issue.status}
      data-type={issue.type}
      data-priority={priorityName}
      data-issue-id={issue.id}
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
            <span className="issue-accent-id">{formatIssueId(issue.id)}</span>
          </div>
          <div className="issue-accent-priority">{priorityName}</div>
        </div>
      </div>
      <div className="grid gap-1 pt-2">
        <h3 className={`text-base font-medium ${isSelected ? "text-selected" : "text-foreground"}`}>{issue.title}</h3>
        <div className="flex items-center justify-end text-xs text-muted">
          {issue.assignee ? <span>{issue.assignee}</span> : null}
        </div>
      </div>
    </div>
  );
}

export const IssueCard = React.memo(IssueCardComponent);
