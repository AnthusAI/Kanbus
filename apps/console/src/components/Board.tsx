import React from "react";
import {
  Board as SharedBoard,
  type KanbanMotionConfig,
} from "@kanbus/ui";
import type { Issue, ProjectConfig } from "../types/issues";

interface BoardProps {
  columns: string[];
  issues: Issue[];
  priorityLookup: Record<number, string>;
  config?: ProjectConfig;
  onSelectIssue?: (issue: Issue) => void;
  selectedIssueId?: string | null;
  transitionKey?: string;
  detailOpen?: boolean;
  collapsedColumns?: Set<string>;
  onToggleCollapse?: (column: string) => void;
  motion?: KanbanMotionConfig;
}

// Keep this wrapper to preserve local import stability while ensuring
// sorting and column behavior stay in sync with the shared UI board.
function BoardComponent(props: BoardProps) {
  return <SharedBoard {...props} />;
}

export const Board = React.memo(BoardComponent);
