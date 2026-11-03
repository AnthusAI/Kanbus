import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { defaultRangeExtractor, useVirtualizer, type Range } from "@tanstack/react-virtual";
import type { KanbanConfig, KanbanIssue } from "./types";
import { IssueCard } from "./IssueCard";
import type { KanbanMotionConfig } from "./motion";

export interface StackedBoardSection {
  columnKey: string;
  title: string;
  issues: KanbanIssue[];
  collapsed: boolean;
  onToggleCollapse?: () => void;
}

export interface StackedBoardProps {
  sections: StackedBoardSection[];
  priorityLookup: Record<number, string>;
  config?: KanbanConfig;
  onSelectIssue?: (issue: KanbanIssue) => void;
  selectedIssueId?: string | null;
  motion?: KanbanMotionConfig;
  revealSelectedIssueOnMount?: boolean;
}

type StackedRow =
  | { kind: "header"; key: string; sectionIndex: number }
  | { kind: "card"; key: string; sectionIndex: number; issue: KanbanIssue; indexWithinSection: number };

const SECTION_HEADER_HEIGHT_PIXELS = 40;
const ESTIMATED_CARD_HEIGHT_PIXELS = 132;
const OVERSCAN_ROW_COUNT = 6;
const INITIAL_VIEWPORT_HEIGHT_PIXELS = 900;

function buildFlatRows(sections: StackedBoardSection[]): StackedRow[] {
  const rows: StackedRow[] = [];
  sections.forEach((section, sectionIndex) => {
    rows.push({ kind: "header", key: `header:${section.columnKey}`, sectionIndex });
    if (section.collapsed) {
      return;
    }
    section.issues.forEach((issue, indexWithinSection) => {
      rows.push({ kind: "card", key: `card:${issue.id}`, sectionIndex, issue, indexWithinSection });
    });
  });
  return rows;
}

function SectionHeaderButton({ section, onToggle }: { section: StackedBoardSection; onToggle: () => void }) {
  const displayTitle = section.title.replace(/_/g, " ");
  const { onToggleCollapse, collapsed } = section;
  return (
    <button type="button" className="kb-column-header" onClick={onToggle}
      disabled={!onToggleCollapse} aria-label={`${collapsed ? "Expand" : "Collapse"} ${displayTitle}`}
      aria-expanded={!collapsed} style={{ height: SECTION_HEADER_HEIGHT_PIXELS }}>
      <span className="column-animate-in kb-column-title">{displayTitle}
        {onToggleCollapse && (collapsed
          ? <ChevronRight className="kb-collapse-icon" aria-hidden="true" />
          : <ChevronDown className="kb-collapse-icon" aria-hidden="true" />)}
      </span>
      <span className="column-animate-in">{section.issues.length}</span>
    </button>
  );
}

/**
 * Every status column as a section of one vertical list with one scroller and one virtualizer.
 *
 * The header of the section at the top of the viewport is a separate sticky element, because a
 * sticky element inside absolutely positioned virtual rows cannot stick. Its own virtual row is
 * left empty while it is the pinned one, so each header exists once in the document.
 */
function StackedBoardComponent({ sections, priorityLookup, config, onSelectIssue, selectedIssueId, motion, revealSelectedIssueOnMount = false }: StackedBoardProps) {
  const scrollContainerReference = useRef<HTMLDivElement | null>(null);
  const rows = useMemo(() => buildFlatRows(sections), [sections]);
  const selectedRowIndex = useMemo(
    () => selectedIssueId == null
      ? -1
      : rows.findIndex((row) => row.kind === "card" && row.issue.id === selectedIssueId),
    [rows, selectedIssueId]
  );

  const extractVisibleRange = useCallback(
    (range: Range) => {
      const visibleIndexes = defaultRangeExtractor(range);
      if (selectedRowIndex < 0 || visibleIndexes.includes(selectedRowIndex)) {
        return visibleIndexes;
      }
      return [...visibleIndexes, selectedRowIndex].sort((left, right) => left - right);
    },
    [selectedRowIndex]
  );

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollContainerReference.current,
    estimateSize: (index) => rows[index].kind === "header" ? SECTION_HEADER_HEIGHT_PIXELS : ESTIMATED_CARD_HEIGHT_PIXELS,
    overscan: OVERSCAN_ROW_COUNT,
    getItemKey: (index) => rows[index].key,
    rangeExtractor: extractVisibleRange,
    initialRect: { width: 0, height: INITIAL_VIEWPORT_HEIGHT_PIXELS }
  });

  const virtualItems = virtualizer.getVirtualItems();
  const firstVisibleRowIndex = virtualizer.range?.startIndex ?? 0;
  const pinnedSectionIndex = rows[firstVisibleRowIndex]?.sectionIndex ?? 0;
  const pinnedSection = sections[pinnedSectionIndex];

  const collapseAnchorColumnKeyReference = useRef<string | null>(null);
  const focusPinnedHeaderColumnKeyReference = useRef<string | null>(null);
  const stickyHeaderReference = useRef<HTMLDivElement | null>(null);

  const toggleSection = useCallback((section: StackedBoardSection) => {
    if (!section.collapsed && section.columnKey === pinnedSection?.columnKey) {
      collapseAnchorColumnKeyReference.current = section.columnKey;
      focusPinnedHeaderColumnKeyReference.current = stickyHeaderReference.current?.contains(document.activeElement)
        ? section.columnKey
        : null;
    }
    section.onToggleCollapse?.();
  }, [pinnedSection?.columnKey]);

  useLayoutEffect(() => {
    if (revealSelectedIssueOnMount && selectedRowIndex >= 0) {
      virtualizer.scrollToIndex(selectedRowIndex, { align: "center" });
    }
  }, []);

  useLayoutEffect(() => {
    const anchoredColumnKey = collapseAnchorColumnKeyReference.current;
    if (anchoredColumnKey === null) {
      return;
    }
    const anchoredSectionIndex = sections.findIndex((section) => section.columnKey === anchoredColumnKey);
    if (anchoredSectionIndex < 0 || !sections[anchoredSectionIndex].collapsed) {
      collapseAnchorColumnKeyReference.current = null;
      return;
    }
    collapseAnchorColumnKeyReference.current = null;
    const headerRowIndex = rows.findIndex((row) => row.kind === "header" && row.sectionIndex === anchoredSectionIndex);
    virtualizer.scrollToIndex(headerRowIndex, { align: "start" });
  }, [rows]);

  useEffect(() => {
    const wantedColumnKey = focusPinnedHeaderColumnKeyReference.current;
    if (wantedColumnKey === null || collapseAnchorColumnKeyReference.current !== null) {
      return;
    }
    if (pinnedSection?.columnKey !== wantedColumnKey) {
      return;
    }
    focusPinnedHeaderColumnKeyReference.current = null;
    stickyHeaderReference.current?.querySelector<HTMLButtonElement>(".kb-column-header")?.focus();
  });

  return (
    <div ref={scrollContainerReference} className="kb-stacked-scroll">
      {pinnedSection && (
        <div key={pinnedSection.columnKey} ref={stickyHeaderReference} className="kb-stacked-sticky-header"
          data-column-key={pinnedSection.columnKey}
          style={{ height: SECTION_HEADER_HEIGHT_PIXELS, marginBottom: -SECTION_HEADER_HEIGHT_PIXELS }}>
          <SectionHeaderButton section={pinnedSection} onToggle={() => toggleSection(pinnedSection)} />
        </div>
      )}
      <div className="kb-stacked-rows" style={{ position: "relative", height: virtualizer.getTotalSize() }}>
        {virtualItems.map((virtualItem) => {
          const row = rows[virtualItem.index];
          const section = sections[row.sectionIndex];
          const rowStyle = { position: "absolute" as const, top: virtualItem.start, left: 0, width: "100%" };
          if (row.kind === "header") {
            return (
              <div key={virtualItem.key} ref={virtualizer.measureElement} data-index={virtualItem.index}
                data-column-key={section.columnKey} className="kb-stacked-header-row"
                style={{ ...rowStyle, height: SECTION_HEADER_HEIGHT_PIXELS }}>
                {row.sectionIndex === pinnedSectionIndex ? null : <SectionHeaderButton section={section} onToggle={() => toggleSection(section)} />}
              </div>
            );
          }
          return (
            <div key={virtualItem.key} ref={virtualizer.measureElement} data-index={virtualItem.index}
              data-column-key={section.columnKey} className="kb-column-card-slot"
              style={{ ...rowStyle, paddingBottom: "var(--kb-card-gap, 8px)" }}>
              <IssueCard issue={row.issue} priorityName={priorityLookup[row.issue.priority] ?? "medium"}
                config={config} onSelect={onSelectIssue} isSelected={selectedIssueId === row.issue.id}
                motion={motion} motionIndex={row.indexWithinSection} />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export const StackedBoard = React.memo(StackedBoardComponent);
