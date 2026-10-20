import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef } from "react";
import gsap from "gsap";
import { Flip } from "gsap/Flip";

if (typeof window !== "undefined") {
  gsap.registerPlugin(Flip);
}

import type {
  KanbanConfig,
  KanbanIssue,
  KanbanSortFieldRule,
  KanbanSortPreset,
  KanbanSortRule
} from "./types";
import { BoardColumn } from "./BoardColumn";
import { IssueIdFormatProvider, type IssueIdFormatter } from "./issue-id-format";
import { useBoardColumnState } from "./useBoardColumnState";
import { useBoardTransitions } from "./useBoardTransitions";
import {
  normalizeMotionConfig,
  useReducedMotion,
  type KanbanMotionConfig
} from "./motion";

export interface BoardProps {
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
  /** Optional workspace/account-scoped persistence; default collapse works without a host callback. */
  columnStateKey?: string;
  motion?: KanbanMotionConfig;
  initialScroll?: "start" | "end" | "preserve";
  formatIssueId?: IssueIdFormatter;
}

type IssueComparator = (a: KanbanIssue, b: KanbanIssue) => number;

const DONE_NAMES = new Set(["done", "closed", "complete", "completed", "resolved"]);

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

function compareNullableNumber(
  a: number | undefined,
  b: number | undefined,
  direction: "asc" | "desc"
): number {
  const hasA = Number.isFinite(a);
  const hasB = Number.isFinite(b);
  if (hasA && !hasB) return -1;
  if (!hasA && hasB) return 1;
  if (!hasA && !hasB) return 0;
  const order = (a ?? 0) - (b ?? 0);
  if (order === 0) return 0;
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

function isSortPreset(value: unknown): value is KanbanSortPreset {
  return value === "fifo"
    || value === "priority-first"
    || value === "recently-updated";
}

function isSortField(value: unknown): value is KanbanSortFieldRule["field"] {
  return value === "priority"
    || value === "created_at"
    || value === "updated_at"
    || value === "id";
}

function isSortDirection(value: unknown): value is KanbanSortFieldRule["direction"] {
  return value === "asc" || value === "desc";
}

function parseSortRule(value: unknown): KanbanSortRule | null {
  if (isSortPreset(value)) {
    return value;
  }
  if (!Array.isArray(value) || value.length === 0) {
    return null;
  }

  const parsed: KanbanSortFieldRule[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object") {
      return null;
    }
    const field = (entry as Record<string, unknown>).field;
    const direction = (entry as Record<string, unknown>).direction;
    if (!isSortField(field) || !isSortDirection(direction)) {
      return null;
    }
    parsed.push({ field, direction });
  }
  return parsed;
}

function compareByField(
  rule: KanbanSortFieldRule
): IssueComparator {
  if (rule.field === "priority") {
    return (a, b) => compareNullableNumber(a.priority, b.priority, rule.direction);
  }
  if (rule.field === "created_at") {
    return (a, b) => compareTimestamp(a.created_at, b.created_at, rule.direction);
  }
  if (rule.field === "updated_at") {
    return (a, b) => compareTimestamp(a.updated_at, b.updated_at, rule.direction);
  }
  return (a, b) => compareNullableString(a.id, b.id, rule.direction);
}

function comparatorForPreset(preset: KanbanSortPreset): IssueComparator {
  if (preset === "priority-first") {
    return chainComparators([
      (a, b) => compareNullableNumber(a.priority, b.priority, "asc"),
      (a, b) => compareTimestamp(a.created_at, b.created_at, "asc"),
      compareIdAsc
    ]);
  }
  if (preset === "recently-updated") {
    return chainComparators([
      (a, b) => compareTimestamp(a.updated_at, b.updated_at, "desc"),
      compareIdAsc
    ]);
  }
  return chainComparators([
    (a, b) => compareTimestamp(a.created_at, b.created_at, "asc"),
    compareIdAsc
  ]);
}

function comparatorForRule(rule: KanbanSortRule): IssueComparator {
  if (typeof rule === "string") {
    return comparatorForPreset(rule);
  }

  const comparators = rule.map(compareByField);
  const hasIdRule = rule.some((entry) => entry.field === "id");
  if (!hasIdRule) {
    comparators.push(compareIdAsc);
  }
  return chainComparators(comparators);
}

function resolveConfiguredSortRule(
  column: string,
  config?: KanbanConfig
): KanbanSortRule | null {
  const sortOrder = config?.sort_order;
  if (!sortOrder) {
    return null;
  }

  const statusRule = parseSortRule((sortOrder as Record<string, unknown>)[column]);
  if (statusRule) {
    return statusRule;
  }

  const statusDefinition = config?.statuses.find((status) => status.key === column);
  const categoryName = statusDefinition?.category;
  if (!categoryName) {
    return null;
  }

  const categories = (sortOrder as { categories?: unknown }).categories;
  if (!categories || typeof categories !== "object" || Array.isArray(categories)) {
    return null;
  }
  return parseSortRule((categories as Record<string, unknown>)[categoryName]);
}

function resolveColumnComparator(column: string, config?: KanbanConfig): IssueComparator {
  if (isDoneColumn(column, config)) {
    return comparatorForPreset("recently-updated");
  }
  const configuredRule = resolveConfiguredSortRule(column, config);
  if (configuredRule) {
    return comparatorForRule(configuredRule);
  }
  return comparatorForPreset("fifo");
}

function isDoneColumn(column: string, config?: KanbanConfig): boolean {
  const status = config?.statuses.find((item) => item.key === column);
  if (status?.category) {
    const normalizedCategory = status.category.trim().toLowerCase();
    if (DONE_NAMES.has(normalizedCategory)) {
      return true;
    }
  }
  return DONE_NAMES.has(column.trim().toLowerCase());
}

function motionConfigurationsMatch(previous: KanbanMotionConfig, next: KanbanMotionConfig): boolean {
  return previous.mode === next.mode
    && previous.frame === next.frame
    && previous.fps === next.fps
    && previous.staggerFrames === next.staggerFrames
    && previous.durationFrames === next.durationFrames;
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
  collapsedColumns,
  onToggleCollapse,
  columnStateKey,
  motion,
  initialScroll = "end"
}: Omit<BoardProps, "formatIssueId">) {
  const columnState = useBoardColumnState({ config, columns, storageKey: collapsedColumns === undefined ? columnStateKey : undefined });
  const visibleCollapsedColumns = collapsedColumns ?? columnState.collapsedColumns;
  const toggleColumn = onToggleCollapse ?? (collapsedColumns === undefined ? columnState.toggleColumn : undefined);
  const useIsomorphicLayoutEffect =
    typeof window === "undefined" ? useEffect : useLayoutEffect;
  const reducedMotion = useReducedMotion();
  const resolvedMotion = reducedMotion ? { mode: "static" as const } : normalizeMotionConfig(motion);
  const scope = useBoardTransitions(transitionKey ?? "", resolvedMotion.mode === "css");
  const boardRef = useRef<HTMLDivElement | null>(null);
  const didInitialScroll = useRef(false);

  const flipStateRef = useRef<any>(null);
  const previousIssuesRef = useRef(issues);
  const stableMotionRef = useRef(resolvedMotion);
  if (!motionConfigurationsMatch(stableMotionRef.current, resolvedMotion)) {
    stableMotionRef.current = resolvedMotion;
  }
  const stableMotion = stableMotionRef.current;

  const setBoardRef = useCallback(
    (node: HTMLDivElement | null) => {
      scope.current = node;
      boardRef.current = node;
    },
    [scope]
  );

  if (previousIssuesRef.current !== issues) {
    previousIssuesRef.current = issues;
    if (boardRef.current && stableMotion.mode === "css" && typeof window !== "undefined") {
      const cards = gsap.utils.toArray<HTMLElement>(".issue-card", boardRef.current);
      if (cards.length > 0) {
        flipStateRef.current = Flip.getState(cards, { props: "opacity" });
      }
    }
  }

  useIsomorphicLayoutEffect(() => {
    if (flipStateRef.current && boardRef.current && typeof window !== "undefined") {
      const state = flipStateRef.current;
      flipStateRef.current = null;

      const cards = gsap.utils.toArray<HTMLElement>(".issue-card", boardRef.current);
      if (cards.length > 0) {
        const scrollContainers = boardRef.current?.querySelectorAll('.kb-column-scroll') || [];
        scrollContainers.forEach(col => {
          const el = col as HTMLElement;
          el.style.width = `${el.clientWidth}px`;
          el.style.height = `${el.clientHeight}px`;
          el.style.flex = 'none';
        });

        if (boardRef.current) {
          boardRef.current.classList.add("is-flipping");
        }

        cards.forEach((card) => {
          card.classList.remove("issue-animate-in-up", "issue-animate-in-down");
          card.style.animation = "none";
          card.style.transition = "none";
        });

        Flip.from(state, {
          targets: cards,
          duration: 0.4,
          ease: "power2.out",
          nested: true,
          clearProps: "transform,opacity",
          onComplete: () => {
            if (boardRef.current) {
              boardRef.current.classList.remove("is-flipping");
            }
            scrollContainers.forEach(col => {
              const el = col as HTMLElement;
              el.style.width = '';
              el.style.height = '';
              el.style.flex = '';
            });
            cards.forEach((card) => {
              card.style.animation = "";
              card.style.transition = "";
            });
          },
          zIndex: 10
        });
      }
    }
  }, [issues]);

  useIsomorphicLayoutEffect(() => {
    if (initialScroll === "preserve" || didInitialScroll.current) {
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
    node.scrollLeft = initialScroll === "start" ? 0 : maxScrollLeft;
    didInitialScroll.current = true;
  }, [columns.length, initialScroll]);

  useEffect(() => {
    if (!detailOpen) return;
    const node = boardRef.current;
    if (!node) return;
    const maxScrollLeft = node.scrollWidth - node.clientWidth;
    if (maxScrollLeft <= 0) return;
    node.scrollTo({ left: maxScrollLeft, behavior: reducedMotion ? "auto" : "smooth" });
  }, [detailOpen, reducedMotion]);

  const orderedIssuesByColumn = useMemo(() => {
    const issuesByStatus = new Map<string, KanbanIssue[]>();
    for (const issue of issues) {
      const bucket = issuesByStatus.get(issue.status);
      if (bucket) {
        bucket.push(issue);
      } else {
        issuesByStatus.set(issue.status, [issue]);
      }
    }
    return new Map(
      columns.map((column) => [
        column,
        [...(issuesByStatus.get(column) ?? [])].sort(resolveColumnComparator(column, config))
      ])
    );
  }, [columns, issues, config]);

  const previousColumnIssuesRef = useRef(new Map<string, KanbanIssue[]>());
  const stableOrderedIssuesByColumn = useMemo(() => {
    const stable = new Map<string, KanbanIssue[]>();
    for (const [column, orderedIssues] of orderedIssuesByColumn) {
      const previous = previousColumnIssuesRef.current.get(column);
      const unchanged = previous !== undefined
        && previous.length === orderedIssues.length
        && previous.every((issue, index) => issue === orderedIssues[index]);
      stable.set(column, unchanged ? previous : orderedIssues);
    }
    previousColumnIssuesRef.current = stable;
    return stable;
  }, [orderedIssuesByColumn]);

  const columnToggleHandlers = useMemo(
    () => new Map(columns.map((column) => [column, toggleColumn ? () => toggleColumn(column) : undefined])),
    [columns, toggleColumn]
  );

  return (
    <div ref={setBoardRef} className="kb-grid gap-2" data-motion={stableMotion.mode}>
      {columns.map((column) => {
        const displayTitle =
          config?.statuses.find((status) => status.key === column)?.name ?? column;
        return (
          <BoardColumn
            key={column}
            columnKey={column}
            title={displayTitle}
            issues={stableOrderedIssuesByColumn.get(column) ?? []}
            priorityLookup={priorityLookup}
            config={config}
            onSelectIssue={onSelectIssue}
            selectedIssueId={selectedIssueId}
            collapsed={visibleCollapsedColumns.has(column)}
            onToggleCollapse={columnToggleHandlers.get(column)}
            motion={stableMotion}
          />
        );
      })}
    </div>
  );
}

export const Board = React.memo(function Board({ formatIssueId, ...boardProps }: BoardProps) {
  return (
    <IssueIdFormatProvider formatIssueId={formatIssueId}>
      <BoardComponent {...boardProps} />
    </IssueIdFormatProvider>
  );
});
