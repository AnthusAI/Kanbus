import { useMemo } from "react";
import type { ViewMode } from "../types/console";
import type { Issue, ProjectConfig } from "../types/issues";
import { matchesSearchQuery } from "../utils/issue-search";
import { collectDescendants, getIssueProjectLabel } from "../utils/issue-selection";

type FilteredIssuesOptions = {
  issues: Issue[];
  deferredIssues: Issue[];
  config: ProjectConfig | undefined;
  resolvedViewMode: ViewMode | null;
  parentIssue: Issue | null;
  parentId: string | null;
  focusedIssueId: string | null;
  searchQuery: string;
  enabledProjects: Set<string> | null;
  effectiveEnabledProjects: Set<string>;
  projectLabels: string[];
  showLocal: boolean;
  showShared: boolean;
  showAllTypes: boolean;
  exactIssueType: string | undefined;
};

export type FilteredIssues = {
  filteredIssues: Issue[];
  metricsIssues: Issue[];
  hasLocalIssues: boolean;
};

export function useFilteredIssues({
  issues,
  deferredIssues,
  config,
  resolvedViewMode,
  parentIssue,
  parentId,
  focusedIssueId,
  searchQuery,
  enabledProjects,
  effectiveEnabledProjects,
  projectLabels,
  showLocal,
  showShared,
  showAllTypes,
  exactIssueType,
}: FilteredIssuesOptions): FilteredIssues {
  const hasLocalIssues = useMemo(() => {
    return issues.some((issue) => issue.custom?.source === "local");
  }, [issues]);

  const filteredIssues = useMemo(() => {
    const projectFilterSet = enabledProjects ?? new Set(projectLabels);
    const sourceIssues = issues;
    let result = sourceIssues;
    const hasSearchQuery = searchQuery.trim().length > 0;

    if (focusedIssueId) {
      const ids = collectDescendants(sourceIssues, focusedIssueId);
      result = sourceIssues.filter((issue) => ids.has(issue.id));
    } else if (parentIssue) {
      const ids = collectDescendants(sourceIssues, parentIssue.id);
      result = sourceIssues.filter((issue) => ids.has(issue.id));
    } else if (parentId) {
      result = [];
    } else if (hasSearchQuery) {
      result = sourceIssues;
    } else if (showAllTypes || exactIssueType) {
      result = sourceIssues;
    } else if (resolvedViewMode === "initiatives") {
      result = sourceIssues.filter((issue) => issue.type === "initiative");
    } else if (resolvedViewMode === "epics") {
      result = sourceIssues.filter((issue) => issue.type === "epic");
    } else if (resolvedViewMode === "issues") {
      result = sourceIssues.filter(
        (issue) =>
          issue.type !== "initiative" &&
          issue.type !== "epic" &&
          issue.type !== "sub-task"
      );
    }

    if (exactIssueType) result = result.filter((issue) => issue.type === exactIssueType);

    if (hasSearchQuery) {
      result = result.filter((issue) => matchesSearchQuery(issue, searchQuery));
    }

    if (projectLabels.length > 0) {
      result = result.filter((issue) => {
        const label = getIssueProjectLabel(issue, config ?? null);
        return projectFilterSet.has(label);
      });
    }

    if (!showLocal) {
      result = result.filter((issue) => issue.custom?.source !== "local");
    }
    if (!showShared) {
      result = result.filter((issue) => issue.custom?.source !== "shared");
    }

    return result;
  }, [issues, deferredIssues, resolvedViewMode, parentIssue, parentId, focusedIssueId, searchQuery, enabledProjects, projectLabels.length, showLocal, showShared, showAllTypes, exactIssueType, config]);

  const metricsIssues = useMemo(() => {
    if (!config) {
      return [];
    }
    const projectFilterSet = effectiveEnabledProjects ?? new Set(projectLabels);
    const sourceIssues = issues;
    let result = sourceIssues;
    const hasSearchQuery = searchQuery.trim().length > 0;

    if (focusedIssueId) {
      const ids = collectDescendants(sourceIssues, focusedIssueId);
      result = sourceIssues.filter((issue) => ids.has(issue.id));
    } else if (parentIssue) {
      const ids = collectDescendants(sourceIssues, parentIssue.id);
      result = sourceIssues.filter((issue) => ids.has(issue.id));
    } else if (parentId) {
      result = [];
    } else if (hasSearchQuery) {
      result = sourceIssues;
    }

    if (hasSearchQuery) {
      result = result.filter((issue) => matchesSearchQuery(issue, searchQuery));
    }

    if (projectLabels.length > 0) {
      result = result.filter((issue) => {
        const label = getIssueProjectLabel(issue, config);
        return projectFilterSet.has(label);
      });
    }

    if (!showLocal) {
      result = result.filter((issue) => issue.custom?.source !== "local");
    }
    if (!showShared) {
      result = result.filter((issue) => issue.custom?.source !== "shared");
    }

    return result;
  }, [config, issues, parentIssue, parentId, focusedIssueId, searchQuery, effectiveEnabledProjects, projectLabels.length, showLocal, showShared]);

  return { filteredIssues, metricsIssues, hasLocalIssues };
}
