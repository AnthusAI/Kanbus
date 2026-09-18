import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import gsap from "gsap";
import { Flip } from "gsap/Flip";

if (typeof window !== "undefined") {
  gsap.registerPlugin(Flip);
}

import type {
  KanbanConfig,
  KanbanIssue
} from "./types";
import { BoardColumn } from "./BoardColumn";
import { useBoardTransitions } from "./useBoardTransitions";
import {
  normalizeMotionConfig,
  type KanbanMotionConfig
} from "./motion";

interface BoardProps {
  columns: string[];
  issues: KanbanIssue[];
  priorityLookup: Record<number, string>;
  config?: KanbanConfig;
  onSelectIssue?: (issue: KanbanIssue) => void;
  selectedIssueId?: string | null;
  transitionKey?: string;
  detailOpen?: boolean;
  collapsedColumns?: Set<string>;
  onToggleCollapse?: (column: string) => void;
  motion?: KanbanMotionConfig;
}

type IssueComparator = (a: KanbanIssue, b: KanbanIssue) => number;

function compareNullableString(
  a: string | undefined,
  b: string | undefined,
  direction: "asc" | "desc"
): number {
  const hasA = typeof a === "string" && a.length > 0;
  const hasB = typeof b === "string" && b.length > 0;
  if (hasA && !hasB) return -1;
  if (!hasA && hasB) return 1;
  if (!hasA && !hasB) return 0;
  const order = a! < b! ? -1 : a! > b! ? 1 : 0;
  return direction === "asc" ? order : -order;
}

function parseTimestamp(value: string | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function compareTimestamp(
  a: string | undefined,
  b: string | undefined,
  direction: "asc" | "desc"
): number {
  const parsedA = parseTimestamp(a);
  const parsedB = parseTimestamp(b);
  const hasA = parsedA != null;
  const hasB = parsedB != null;
  if (hasA && !hasB) return -1;
  if (!hasA && hasB) return 1;
  if (!hasA && !hasB) return 0;
  const order = (parsedA ?? 0) - (parsedB ?? 0);
  if (order === 0) return 0;
  return direction === "asc" ? order : -order;
}

function compareIdAsc(a: KanbanIssue, b: KanbanIssue): number {
  return compareNullableString(a.id, b.id, "asc");
}

function chainComparators(comparators: IssueComparator[]): IssueComparator {
  return (a, b) => {
    for (const comparator of comparators) {
      const result = comparator(a, b);
      if (result !== 0) {
        return result;
      }
    }
    return 0;
  };
}

function comparatorForPreset(): IssueComparator {
  return chainComparators([
    (a, b) => compareTimestamp(a.updated_at, b.updated_at, "desc"),
    compareIdAsc
  ]);
}

function BoardComponent({
  columns,
  issues,
  priorityLookup,
  config,
  onSelectIssue,
  selectedIssueId,
  transitionKey,
  detailOpen,
  collapsedColumns = new Set(),
  onToggleCollapse,
  motion
}: BoardProps) {
  const useIsomorphicLayoutEffect =
    typeof window === "undefined" ? useEffect : useLayoutEffect;
  const resolvedMotion = normalizeMotionConfig(motion);
  const scope = useBoardTransitions(transitionKey ?? "", resolvedMotion.mode === "css");
  const boardRef = useRef<HTMLDivElement | null>(null);
  const didInitialScroll = useRef(false);

  const [renderedIssues, setRenderedIssues] = useState(issues);
  const flipStateRef = useRef<any>(null);

  const setBoardRef = useCallback(
    (node: HTMLDivElement | null) => {
      scope.current = node;
      boardRef.current = node;
    },
    [scope]
  );

  useIsomorphicLayoutEffect(() => {
    if (issues !== renderedIssues) {
      if (boardRef.current && resolvedMotion.mode === "css" && typeof window !== "undefined") {
        const cards = gsap.utils.toArray<HTMLElement>(".issue-card", boardRef.current);
        if (cards.length > 0) {
          console.log("[Board] Capturing Flip state for", cards.length, "cards");
          flipStateRef.current = Flip.getState(cards, { props: "opacity" });
        }
      }
      setRenderedIssues(issues);
    }
  }, [issues, renderedIssues, resolvedMotion.mode]);

  useIsomorphicLayoutEffect(() => {
    if (flipStateRef.current && boardRef.current && typeof window !== "undefined") {
      const state = flipStateRef.current;
      flipStateRef.current = null;
      
      const cards = gsap.utils.toArray<HTMLElement>(".issue-card", boardRef.current);
      console.log("[Board] Running Flip from state to", cards.length, "cards", state);
      if (cards.length > 0) {
        // Freeze container dimensions to prevent layout shifts when overflow: visible removes scrollbars
        const scrollContainers = boardRef.current?.querySelectorAll('.kb-column-scroll') || [];
        scrollContainers.forEach(col => {
          const el = col as HTMLElement;
          el.style.width = `${el.clientWidth}px`;
          el.style.height = `${el.clientHeight}px`;
          el.style.flex = 'none'; // Prevent flex resizing
        });

        if (boardRef.current) {
          boardRef.current.classList.add("is-flipping");
        }

        // Remove animation classes from all cards before flipping
        cards.forEach((card) => {
          card.classList.remove("issue-animate-in-up", "issue-animate-in-down");
          card.style.animation = "none"; // Temporarily suppress CSS animations
          card.style.transition = "none"; // Ensure transition doesn't interfere
        });

        Flip.from(state, {
          targets: cards,
          duration: 0.4,
          ease: "power2.out",
          nested: true,
          clearProps: "transform,opacity",
          onComplete: () => {
            console.log("[Board] Flip complete");
            if (boardRef.current) {
              boardRef.current.classList.remove("is-flipping");
            }
            // Unfreeze container dimensions
            scrollContainers.forEach(col => {
              const el = col as HTMLElement;
              el.style.width = '';
              el.style.height = '';
              el.style.flex = '';
            });
            // Restore animation styling just in case
            cards.forEach((card) => {
              card.style.animation = "";
              card.style.transition = "";
            });
          },
          zIndex: 10
        });
      }
    }
  }, [renderedIssues]);

  useIsomorphicLayoutEffect(() => {
    if (didInitialScroll.current) {
      return;
    }
    const node = boardRef.current;
    if (!node) {
      return;
    }
    const maxScrollLeft = node.scrollWidth - node.clientWidth;
    if (maxScrollLeft <= 0) {
      return;
    }
    node.scrollLeft = maxScrollLeft;
    didInitialScroll.current = true;
  }, [columns.length]);

  useEffect(() => {
    if (!detailOpen) return;
    const node = boardRef.current;
    if (!node) return;
    const maxScrollLeft = node.scrollWidth - node.clientWidth;
    if (maxScrollLeft <= 0) return;
    node.scrollTo({ left: maxScrollLeft, behavior: "smooth" });
  }, [detailOpen]);

  return (
    <div ref={setBoardRef} className="kb-grid gap-2">
      {columns.map((column) => {
        const columnIssues = renderedIssues.filter((issue) => issue.status === column);
        const orderedIssues = [...columnIssues].sort(comparatorForPreset());
        const displayTitle =
          config?.statuses.find((status) => status.key === column)?.name ?? column;
        return (
          <BoardColumn
            key={column}
            columnKey={column}
            title={displayTitle}
            issues={orderedIssues}
            priorityLookup={priorityLookup}
            config={config}
            onSelectIssue={onSelectIssue}
            selectedIssueId={selectedIssueId}
            collapsed={collapsedColumns.has(column)}
            onToggleCollapse={() => onToggleCollapse?.(column)}
            motion={resolvedMotion}
          />
        );
      })}
    </div>
  );
}

export const Board = React.memo(BoardComponent);
