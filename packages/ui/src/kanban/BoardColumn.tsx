import React, { useCallback, useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { defaultRangeExtractor, useVirtualizer, type Range } from "@tanstack/react-virtual";
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

const ESTIMATED_CARD_HEIGHT_PIXELS = 132;
const OVERSCAN_CARD_COUNT = 6;
const INITIAL_VIEWPORT_HEIGHT_PIXELS = 900;

function BoardColumnComponent({ columnKey, title, issues, priorityLookup, config, onSelectIssue,
  selectedIssueId, collapsed = false, onToggleCollapse, motion }: BoardColumnProps) {
  const displayTitle = title.replace(/_/g, " ");
  const scrollContainerReference = useRef<HTMLDivElement | null>(null);
  const selectedIndex = selectedIssueId == null ? -1 : issues.findIndex((issue) => issue.id === selectedIssueId);

  const extractVisibleRange = useCallback(
    (range: Range) => {
      const visibleIndexes = defaultRangeExtractor(range);
      if (selectedIndex < 0 || visibleIndexes.includes(selectedIndex)) {
        return visibleIndexes;
      }
      return [...visibleIndexes, selectedIndex].sort((left, right) => left - right);
    },
    [selectedIndex]
  );

  const virtualizer = useVirtualizer({
    count: collapsed ? 0 : issues.length,
    getScrollElement: () => scrollContainerReference.current,
    estimateSize: () => ESTIMATED_CARD_HEIGHT_PIXELS,
    overscan: OVERSCAN_CARD_COUNT,
    getItemKey: (index) => issues[index].id,
    rangeExtractor: extractVisibleRange,
    initialRect: { width: 0, height: INITIAL_VIEWPORT_HEIGHT_PIXELS }
  });

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
      {!collapsed && <div ref={scrollContainerReference} className="kb-column-scroll mt-1 flex-1 min-h-0 overflow-y-auto">
        <div className="min-h-[50px]" style={{ display: "block", position: "relative", height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((virtualItem) => {
            const issue = issues[virtualItem.index];
            return (
              <div key={virtualItem.key} ref={virtualizer.measureElement} className="kb-column-card-slot" data-index={virtualItem.index}
                style={{ position: "absolute", top: virtualItem.start, left: 0, width: "100%",
                  paddingBottom: "var(--kb-card-gap, 8px)" }}>
                <IssueCard issue={issue}
                  priorityName={priorityLookup[issue.priority] ?? "medium"} config={config}
                  onSelect={onSelectIssue} isSelected={selectedIssueId === issue.id} motion={motion}
                  motionIndex={virtualItem.index} />
              </div>
            );
          })}
        </div>
      </div>}
    </div>
  );
}

export const BoardColumn = React.memo(BoardColumnComponent);
