import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { KanbanConfig, KanbanIssue } from "./types";
import { IssueCard } from "./IssueCard";
import type { KanbanMotionConfig } from "./motion";

interface BoardColumnProps {
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

export function BoardColumn({
  title,
  issues,
  priorityLookup,
  config,
  onSelectIssue,
  selectedIssueId,
  collapsed = false,
  onToggleCollapse,
  motion
}: BoardColumnProps) {
  if (collapsed) {
    return (
      <div
        className="kb-column flex flex-col items-center h-full min-h-0 cursor-pointer opacity-60 hover:opacity-100 transition-opacity"
        style={{ minWidth: "48px", maxWidth: "48px" }}
        onClick={onToggleCollapse}
        title={`${title.replace(/_/g, " ")} (${issues.length}) - Click to expand`}
      >
        <div className="h-7 flex items-center justify-center px-2 w-full">
          <span className="text-xs font-semibold">{issues.length}</span>
        </div>
        <div className="flex flex-col items-center px-2">
          <span
            className="text-xs font-semibold uppercase tracking-wider"
            style={{
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
              whiteSpace: "nowrap"
            }}
          >
            {title.replace(/_/g, " ")}
          </span>
        </div>
        <div className="h-7 flex items-center justify-center px-2 w-full">
          <ChevronRight className="w-4 h-4 text-muted" aria-hidden="true" />
        </div>
      </div>
    );
  }

  return (
    <div className="kb-column flex flex-col h-full min-h-0">
      <div
        className="kb-column-header h-7 items-center flex justify-between px-3 cursor-pointer hover:opacity-80 transition-opacity"
        onClick={onToggleCollapse}
        title="Click to collapse"
      >
        <span className="column-animate-in inline-flex items-center gap-0 min-w-0">
          <span className="min-w-0 truncate">{title.replace(/_/g, " ")}</span>
          <ChevronLeft className="w-4 h-4 text-muted shrink-0" aria-hidden="true" />
        </span>
        <span className="column-animate-in pr-1">{issues.length}</span>
      </div>
      <div className="kb-column-scroll mt-1 flex-1 min-h-0 overflow-y-auto">
        <div className="grid gap-2" key={`${title}-issues`}>
          {issues.map((issue, index) => (
            <IssueCard
              key={issue.id}
              issue={issue}
              priorityName={priorityLookup[issue.priority] ?? "medium"}
              config={config}
              onSelect={onSelectIssue}
              isSelected={selectedIssueId === issue.id}
              motion={motion}
              motionIndex={index}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
