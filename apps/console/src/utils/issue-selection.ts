import type { Issue, IssuesSnapshot, ProjectConfig } from "../types/issues";
import type { IssueSelectionContext, RouteContext, ViewMode } from "../types/console";
import type { BoardTypeFilter } from "@kanbus/ui";

function shortIdMatches(
  candidate: string,
  projectKey: string,
  fullId: string
): boolean {
  if (!candidate.startsWith(`${projectKey}-`)) {
    return false;
  }
  const prefix = candidate.slice(projectKey.length + 1);
  if (prefix.length === 0 || prefix.length > 6) {
    return false;
  }
  if (!fullId.startsWith(`${projectKey}-`)) {
    return false;
  }
  const suffix = fullId.slice(projectKey.length + 1);
  return suffix.startsWith(prefix);
}

export function resolveIssueByIdentifier(
  issues: Issue[],
  identifier: string,
  projectKey: string
): { issue: Issue | null; error: string | null } {
  const matches = issues.filter(
    (issue) => issue.id === identifier || shortIdMatches(identifier, projectKey, issue.id)
  );
  if (matches.length === 0) {
    return { issue: null, error: "Issue not found for URL id" };
  }
  if (matches.length > 1) {
    return { issue: null, error: "Issue id is ambiguous" };
  }
  return { issue: matches[0], error: null };
}

export function getIssueProjectLabel(issue: Issue, config: ProjectConfig | null): string {
  if (!config) {
    return issue.custom?.project_label as string || issue.id.split("-")[0];
  }
  // In single-project Beads compatibility mode (no virtual projects), treat all
  // issues as belonging to the configured project key so they aren't filtered
  // out by prefix mismatches in legacy Beads IDs (e.g., tskl-*).
  const hasVirtuals = config.virtual_projects && Object.keys(config.virtual_projects).length > 0;
  if (config.beads_compatibility && !hasVirtuals) {
    return config.project_key;
  }

  const explicit = issue.custom?.project_label as string | undefined;
  if (explicit) {
    return explicit;
  }
  const parts = issue.id.split("-");
  if (parts.length > 1) {
    const prefix = parts[0];
    if (prefix === config.project_key) {
      return config.project_key;
    }
    if (config.virtual_projects && Object.keys(config.virtual_projects).includes(prefix)) {
      return prefix;
    }
    // Fall back to the observed prefix so metrics/filtering work even when virtual_projects are not configured
    if (prefix) {
      return prefix;
    }
  }
  return config.project_key;
}

export function collectDescendants(issues: Issue[], parentId: string): Set<string> {
  const childrenByParent = new Map<string, string[]>();
  issues.forEach((issue) => {
    if (!issue.parent) {
      return;
    }
    const existing = childrenByParent.get(issue.parent) ?? [];
    existing.push(issue.id);
    childrenByParent.set(issue.parent, existing);
  });
  const ids = new Set<string>();
  const queue = [parentId];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current || ids.has(current)) {
      continue;
    }
    ids.add(current);
    const children = childrenByParent.get(current) ?? [];
    children.forEach((child) => queue.push(child));
  }
  return ids;
}

export function buildPriorityLookup(config: ProjectConfig): Record<number, string> {
  return Object.entries(config.priorities).reduce<Record<number, string>>(
    (accumulator, [key, value]) => {
      accumulator[Number(key)] = value.name;
      return accumulator;
    },
    {}
  );
}

export function resolveBoardTypeFilter(
  showAllTypes: boolean,
  viewMode: ViewMode | null
): BoardTypeFilter {
  if (showAllTypes) {
    return "all";
  }
  return viewMode ?? "issues";
}

export function computeViewModeCounts(issues: Issue[]): Record<ViewMode, number> {
  return issues.reduce<Record<ViewMode, number>>(
    (accumulator, issue) => {
      if (issue.type === "initiative") {
        accumulator.initiatives += 1;
      } else if (issue.type === "epic") {
        accumulator.epics += 1;
      } else if (
        issue.type !== "initiative"
        && issue.type !== "epic"
        && issue.type !== "sub-task"
      ) {
        accumulator.issues += 1;
      }
      return accumulator;
    },
    { initiatives: 0, epics: 0, issues: 0 }
  );
}

export function selectNonEmptyViewMode(counts: Record<ViewMode, number>): ViewMode {
  if (counts.initiatives > 0) {
    return "initiatives";
  }
  if (counts.epics > 0) {
    return "epics";
  }
  return "issues";
}

export function resolveRouteContext(
  route: RouteContext,
  snapshot: IssuesSnapshot | null,
  viewMode: ViewMode | null
): IssueSelectionContext {
  if (route.basePath == null) {
    return {
      viewMode: null,
      selectedIssue: null,
      parentIssue: null,
      error: route.error
    };
  }
  const routeViewMode = route.parentId ? null : route.viewMode;
  if (!snapshot) {
    return {
      viewMode: routeViewMode ?? viewMode ?? null,
      selectedIssue: null,
      parentIssue: null,
      error: route.error
    };
  }
  if (routeViewMode) {
    return {
      viewMode: routeViewMode,
      selectedIssue: null,
      parentIssue: null,
      error: route.error
    };
  }
  const { issueId, parentId } = route;
  const projectKey = snapshot.config.project_key;
  const parentIssue = parentId
    ? resolveIssueByIdentifier(snapshot.issues, parentId, projectKey)
    : null;
  const selectedIssue = issueId
    ? resolveIssueByIdentifier(snapshot.issues, issueId, projectKey)
    : null;
  if (parentIssue?.error) {
    return {
      viewMode: null,
      selectedIssue: null,
      parentIssue: null,
      error: parentIssue.error
    };
  }
  if (parentIssue?.issue) {
    const parentType = parentIssue.issue.type;
    if (parentType !== "initiative" && parentType !== "epic") {
      return {
        viewMode: null,
        selectedIssue: null,
        parentIssue: null,
        error: "Context parent must be an initiative or epic"
      };
    }
  }
  if (selectedIssue?.error) {
    return {
      viewMode: null,
      selectedIssue: null,
      parentIssue: null,
      error: selectedIssue.error
    };
  }
  if (parentId) {
    if (selectedIssue?.issue) {
      const allowedIds = collectDescendants(snapshot.issues, parentId);
      if (!allowedIds.has(selectedIssue.issue.id)) {
        return {
          viewMode: null,
          selectedIssue: null,
          parentIssue: null,
          error: "Selected issue is not a descendant of the context parent"
        };
      }
    }
    return {
      viewMode: null,
      selectedIssue: selectedIssue?.issue ?? null,
      parentIssue: parentIssue?.issue ?? null,
      error: null
    };
  }
  if (selectedIssue?.issue) {
    const type = selectedIssue.issue.type;
    const derivedViewMode: ViewMode =
      type === "initiative"
        ? "initiatives"
        : type === "epic"
        ? "epics"
        : "issues";
    return {
      viewMode: derivedViewMode,
      selectedIssue: selectedIssue.issue,
      parentIssue: null,
      error: null
    };
  }
  return {
    viewMode: viewMode ?? null,
    selectedIssue: null,
    parentIssue: null,
    error: route.error
  };
}
