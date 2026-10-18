import React, { useRef, useEffect, useLayoutEffect, useState } from "react";
import type { KanbanConfig, KanbanIssue } from "./types";
import { buildIssueColorStyle } from "./issue-colors";
import { formatIssueId } from "./format-issue-id";
import { getTypeIcon } from "./issue-icons";
import {
  getIssueMotionStyle,
  normalizeMotionConfig,
  useReducedMotion,
  type KanbanMotionConfig
} from "./motion";

export interface IssueCardProps {
  issue: KanbanIssue;
  priorityName: string;
  config?: KanbanConfig;
  onSelect?: (issue: KanbanIssue) => void;
  isSelected?: boolean;
  motion?: KanbanMotionConfig;
  motionIndex?: number;
}

interface IssueCardExcerptProps {
  text: string;
}

function IssueCardExcerpt({ text }: IssueCardExcerptProps) {
  const paragraphRef = useRef<HTMLParagraphElement | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflowing, setOverflowing] = useState(false);

  useLayoutEffect(() => {
    const paragraph = paragraphRef.current;
    if (paragraph && !expanded) {
      setOverflowing(paragraph.scrollHeight > paragraph.clientHeight + 1);
    }
  }, [text, expanded]);

  return (
    <div className="issue-card-excerpt" data-expanded={expanded ? "true" : "false"}>
      <p ref={paragraphRef}>{text}</p>
      {overflowing || expanded ? (
        <button
          type="button"
          className="issue-card-excerpt-toggle"
          aria-expanded={expanded}
          onClick={(event) => {
            event.stopPropagation();
            setExpanded((value) => !value);
          }}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {expanded ? "Less" : "More"}
        </button>
      ) : null}
    </div>
  );
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
  const reducedMotion = useReducedMotion();
  const resolvedMotion = reducedMotion ? { mode: "static" as const } : normalizeMotionConfig(motion);

  const handleClick = () => {
    if (onSelect) {
      onSelect(issue);
    }
  };

  useEffect(() => {
    // When the card mounts or updates, if it has inline transforms (from a previous FLIP), clear them.
    // This fixes the issue where a flipped card permanently holds a translated transform that messes up future state changes.
    if (cardRef.current) {
      cardRef.current.style.transform = "";
    }
  }, [issue.status, issue.id]);

  const IssueTypeIcon = getTypeIcon(issue.type, issue.status);
  const issueStyle = config ? buildIssueColorStyle(config, issue) : undefined;
  const motionStyle = getIssueMotionStyle(resolvedMotion, motionIndex);
  const selectionStyle = isSelected
    ? { boxShadow: "var(--kb-card-selected-shadow, inset 0 0 0 6px var(--text-muted))" }
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
      data-flip-id={issue.id}
      data-selected={isSelected ? "true" : undefined}
      onClick={handleClick}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
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
      <div className="issue-card-content grid gap-1 pt-2">
        <h3 className={`text-base font-medium ${isSelected ? "text-selected" : "text-foreground"}`}>
          {issue.title}
        </h3>
        {issue.excerpt ? <IssueCardExcerpt text={issue.excerpt} /> : null}
        <div className="issue-card-owner flex items-center justify-end text-xs text-muted">
          {issue.assignee ? <span>{issue.assignee}</span> : null}
        </div>
      </div>
    </div>
  );
}
