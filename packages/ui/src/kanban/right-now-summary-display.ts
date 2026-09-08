export const RIGHT_NOW_PLACEHOLDER = "(no right-now summary)";
export const RIGHT_NOW_LOADING_SUMMARY = "Generating right-now summary...";
export const RIGHT_NOW_UNAVAILABLE_SUMMARY = "Right-now summary unavailable";

export type RightNowSummaryDisplayMode = "placeholder" | "loading" | "unavailable";

export function resolveRightNowSummaryText(
  summary: string | null | undefined,
  displayMode: RightNowSummaryDisplayMode
): string {
  if (summary != null && summary.trim().length > 0) {
    return summary;
  }
  if (displayMode === "loading") {
    return RIGHT_NOW_LOADING_SUMMARY;
  }
  if (displayMode === "unavailable") {
    return RIGHT_NOW_UNAVAILABLE_SUMMARY;
  }
  return RIGHT_NOW_PLACEHOLDER;
}
