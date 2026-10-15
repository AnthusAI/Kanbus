import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { KanbanConfig, KanbanIssue } from "./types";
import { IssueCard } from "./IssueCard";
import type { KanbanMotionConfig } from "./motion";

export interface BoardColumnProps {
  columnKey?: string;
  title: string;
  issues: KanbanIssue[];
  priorityLookup: Record<number, string>;
  config?: KanbanConfig;
  onSelectIssue?: (issue: KanbanIssue) => void;
  selectedIssueId?: string | null;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  motion?: KanbanMotionConfig;
}

export function BoardColumn({ columnKey, title, issues, priorityLookup, config, onSelectIssue,
  selectedIssueId, collapsed = false, onToggleCollapse, motion }: BoardColumnProps) {
  const displayTitle = title.replace(/_/g, " ");
  return (
    <div className={`kb-column flex flex-col h-full min-h-0${collapsed ? " kb-column-collapsed" : ""}`} data-column-key={columnKey}>
      <button type="button" className="kb-column-header" onClick={onToggleCollapse}
        disabled={!onToggleCollapse} aria-label={`${collapsed ? "Expand" : "Collapse"} ${displayTitle}`}
        aria-expanded={!collapsed}>
        <span className="column-animate-in kb-column-title">{displayTitle}
          {onToggleCollapse && (collapsed ? <ChevronRight className="kb-collapse-icon" aria-hidden="true" /> : <ChevronLeft className="kb-collapse-icon" aria-hidden="true" />)}
        </span>
        <span className="column-animate-in">{issues.length}</span>
      </button>
      {!collapsed && <div className="kb-column-scroll mt-1 flex-1 min-h-0 overflow-y-auto">
        <div className="grid gap-2 min-h-[50px]">
          {issues.map((issue, index) => <IssueCard key={issue.id} issue={issue}
            priorityName={priorityLookup[issue.priority] ?? "medium"} config={config}
            onSelect={onSelectIssue} isSelected={selectedIssueId === issue.id} motion={motion} motionIndex={index} />)}
        </div>
      </div>}
    </div>
  );
}
