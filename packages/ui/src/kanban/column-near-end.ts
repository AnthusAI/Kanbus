import { useCallback, useRef } from "react";

export const DEFAULT_COLUMN_NEAR_END_THRESHOLD = 10;

export type ColumnNearEndReporter = (columnKey: string, issueCount: number) => void;

export function isLastCardWithinThresholdOfRangeEnd(
  lastCardIndex: number,
  renderedRangeEndIndex: number,
  thresholdInCards: number
): boolean {
  return lastCardIndex - renderedRangeEndIndex <= thresholdInCards;
}

/**
 * Returns a stable reporter that calls the host callback at most once per column and issue count.
 *
 * The latest callback is read from a reference, so a new inline function on every render neither
 * changes the reporter identity nor causes a repeat call.
 */
export function useColumnNearEndReporter(
  onColumnNearEnd: ((columnKey: string) => void) | undefined
): ColumnNearEndReporter | undefined {
  const latestCallbackReference = useRef(onColumnNearEnd);
  latestCallbackReference.current = onColumnNearEnd;
  const reportedIssueCountByColumnReference = useRef(new Map<string, number>());

  const reporter = useCallback<ColumnNearEndReporter>((columnKey, issueCount) => {
    if (reportedIssueCountByColumnReference.current.get(columnKey) === issueCount) {
      return;
    }
    reportedIssueCountByColumnReference.current.set(columnKey, issueCount);
    latestCallbackReference.current?.(columnKey);
  }, []);

  return onColumnNearEnd === undefined ? undefined : reporter;
}
