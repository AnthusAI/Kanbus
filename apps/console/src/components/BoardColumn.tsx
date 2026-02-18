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
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

export function BoardColumn({
  title,
  issues,
  priorityLookup,
  config,
  onSelectIssue,
  selectedIssueId,
  collapsed = false,
  onToggleCollapse
}: BoardColumnProps) {
  // Placeholder for collapsed state - full UI in separate issue
  if (collapsed) {
    return (
      <div
        className="kb-column flex flex-col h-full min-h-0 cursor-pointer opacity-60 hover:opacity-100 transition-opacity"
        style={{ minWidth: "48px", maxWidth: "48px" }}
        onClick={onToggleCollapse}
        title={`${title.replace(/_/g, " ")} (${issues.length}) - Click to expand`}
      >
        <div className="flex flex-col items-center justify-start pt-3 px-2">
          <span className="text-xs font-semibold mb-2">{issues.length}</span>
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
        <span className="column-animate-in">{title.replace(/_/g, " ")}</span>
        <span className="pr-3 column-animate-in">{issues.length}</span>
      </div>
      <div className="kb-column-scroll mt-1 flex-1 min-h-0 overflow-y-auto">
        <div className="grid gap-2" key={`${title}-issues`}>
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
