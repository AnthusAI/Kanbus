import { useMemo } from "react";
import {
  buildShortIdWidths,
  effectiveShortIdLength
} from "@kanbus/ui";
import type { Issue, ProjectConfig } from "../types/issues";

/**
 * Derive display widths for short IDs from the currently visible issues.
 * Re-runs whenever the visible set changes (filters, search, columns,
 * trees) so every displayed ID stays unique within the view.
 */
export function useDisplayIdWidths(
  issues: Issue[],
  config: ProjectConfig | null | undefined
): Record<string, number> {
  return useMemo(() => {
    const defaultLen = effectiveShortIdLength(config);
    return buildShortIdWidths(
      issues.map((issue) => issue.id),
      defaultLen
    );
  }, [issues, config]);
}
