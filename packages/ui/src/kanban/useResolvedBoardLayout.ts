import { useCallback, useSyncExternalStore } from "react";

/** How a board arranges its status columns: by viewport width, or forced. */
export type BoardLayout = "auto" | "columns" | "stacked";

/** The layout a board actually renders once "auto" has been resolved. */
export type ResolvedBoardLayout = "columns" | "stacked";

export const DEFAULT_STACKED_BELOW_WIDTH_PIXELS = 600;

const THRESHOLD_WIDTH_EXCLUSION_EPSILON_PIXELS = 0.02;

function buildNarrowViewportQuery(stackedBelowWidth: number): string {
  return `(max-width: ${stackedBelowWidth - THRESHOLD_WIDTH_EXCLUSION_EPSILON_PIXELS}px)`;
}

function readServerSnapshotAsWideViewport(): boolean {
  return false;
}

/**
 * Resolve a board layout setting to "columns" or "stacked".
 *
 * "auto" follows the viewport width through matchMedia, never the width of the
 * board's container, so a detail panel narrowing the board cannot flip the layout.
 * Server rendering and the first hydration pass use "columns".
 */
export function useResolvedBoardLayout(
  layout: BoardLayout = "auto",
  stackedBelowWidth: number = DEFAULT_STACKED_BELOW_WIDTH_PIXELS
): ResolvedBoardLayout {
  const query = buildNarrowViewportQuery(stackedBelowWidth);
  const subscribeToViewportChanges = useCallback(
    (notifyViewportChanged: () => void) => {
      const mediaQueryList = window.matchMedia(query);
      mediaQueryList.addEventListener("change", notifyViewportChanged);
      return () => mediaQueryList.removeEventListener("change", notifyViewportChanged);
    },
    [query]
  );
  const readViewportIsNarrow = useCallback(() => window.matchMedia(query).matches, [query]);
  const viewportIsNarrow = useSyncExternalStore(
    subscribeToViewportChanges,
    readViewportIsNarrow,
    readServerSnapshotAsWideViewport
  );
  if (layout === "columns" || layout === "stacked") {
    return layout;
  }
  return viewportIsNarrow ? "stacked" : "columns";
}
