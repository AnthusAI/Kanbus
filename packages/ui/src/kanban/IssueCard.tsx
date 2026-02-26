import React, { useRef } from "react";
import type { KanbanConfig, KanbanIssue } from "./types";
import { buildIssueColorStyle } from "./issue-colors";
import { formatIssueId } from "./format-issue-id";
import { getTypeIcon } from "./issue-icons";
import {
  getIssueMotionStyle,
  normalizeMotionConfig,
  type KanbanMotionConfig
} from "./motion";

interface IssueCardProps {
  issue: KanbanIssue;
  priorityName: string;
  config?: KanbanConfig;
  onSelect?: (issue: KanbanIssue) => void;
  isSelected?: boolean;
  motion?: KanbanMotionConfig;
  motionIndex?: number;
}

export function IssueCard({
  issue,
  priorityName,
  config,
  onSelect,
  isSelected,
  motion,
  motionIndex = 0
}: IssueCardProps) {
  const cardRef = useRef<HTMLDivElement | null>(null);
  const resolvedMotion = normalizeMotionConfig(motion);

  const handleClick = () => {
    if (onSelect) {
      onSelect(issue);
    }
  };

  const IssueTypeIcon = getTypeIcon(issue.type, issue.status);
  const issueStyle = config ? buildIssueColorStyle(config, issue) : undefined;
  const motionStyle = getIssueMotionStyle(resolvedMotion, motionIndex);
  const selectionStyle = isSelected
    ? { boxShadow: "inset 0 0 0 6px var(--text-muted)" }
    : undefined;
  const combinedStyle = { ...issueStyle, ...motionStyle, ...selectionStyle };

  return (
    <div
      ref={cardRef}
      className={`issue-card rounded-xl bg-card p-3 grid cursor-pointer overflow-hidden relative hover:bg-card-muted transition-shadow duration-300 ${isSelected ? " ring-inset ring-[6px] ring-[var(--text-muted)]" : ""}`}
      style={combinedStyle}
      data-status={issue.status}
      data-type={issue.type}
      data-priority={priorityName}
      data-issue-id={issue.id}
      data-selected={isSelected ? "true" : undefined}
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
        <h3 className={`text-base font-medium ${isSelected ? "text-selected" : "text-foreground"}`}>
          {issue.title}
        </h3>
        <div className="flex items-center justify-end text-xs text-muted">
          {issue.assignee ? <span>{issue.assignee}</span> : null}
        </div>
      </div>
    </div>
  );
}
