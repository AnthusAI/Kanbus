import { describe, expect, it } from "vitest";
import type { Issue, IssuesSnapshot, ProjectConfig } from "../types/issues";
import type { RouteContext } from "../types/console";
import {
  buildPriorityLookup,
  collectDescendants,
  computeViewModeCounts,
  getIssueProjectLabel,
  resolveBoardTypeFilter,
  resolveIssueByIdentifier,
  resolveRouteContext,
  selectNonEmptyViewMode
} from "./issue-selection";

function makeIssue(overrides: Partial<Issue> & { id: string }): Issue {
  return { title: overrides.id, type: "task", status: "open", priority: 2, ...overrides };
}

function makeConfig(overrides: Partial<ProjectConfig> = {}): ProjectConfig {
  return {
    project_key: "kbs",
    virtual_projects: {},
    beads_compatibility: false,
    priorities: { 1: { name: "high" }, 2: { name: "medium" } },
    ...overrides
  } as unknown as ProjectConfig;
}

function makeRoute(overrides: Partial<RouteContext> = {}): RouteContext {
  return {
    account: null,
    project: null,
    basePath: "",
    viewMode: null,
    issueId: null,
    parentId: null,
    wikiPath: null,
    search: null,
    focused: null,
    comment: null,
    typeFilter: null,
    error: null,
    ...overrides
  };
}

function makeSnapshot(issues: Issue[]): IssuesSnapshot {
  return { config: makeConfig(), issues } as unknown as IssuesSnapshot;
}

describe("resolveIssueByIdentifier", () => {
  const issues = [makeIssue({ id: "kbs-abcdef123" }), makeIssue({ id: "kbs-abc999999" })];

  it("matches a full id", () => {
    expect(resolveIssueByIdentifier(issues, "kbs-abcdef123", "kbs").issue?.id).toBe("kbs-abcdef123");
  });

  it("matches a unique short prefix", () => {
    expect(resolveIssueByIdentifier(issues, "kbs-abcd", "kbs").issue?.id).toBe("kbs-abcdef123");
  });

  it("reports ambiguous prefixes", () => {
    expect(resolveIssueByIdentifier(issues, "kbs-abc", "kbs").error).toBe("Issue id is ambiguous");
  });

  it("reports missing issues and rejects prefixes longer than six characters", () => {
    expect(resolveIssueByIdentifier(issues, "kbs-zzz", "kbs").error).toBe("Issue not found for URL id");
    expect(resolveIssueByIdentifier(issues, "kbs-abcdef1", "kbs").error).toBe("Issue not found for URL id");
  });
});

describe("getIssueProjectLabel", () => {
  it("falls back to custom label or id prefix without config", () => {
    expect(getIssueProjectLabel(makeIssue({ id: "tsk-1" }), null)).toBe("tsk");
    expect(getIssueProjectLabel(makeIssue({ id: "tsk-1", custom: { project_label: "x" } }), null)).toBe("x");
  });

  it("uses the project key in single project beads compatibility mode", () => {
    const config = makeConfig({ beads_compatibility: true });
    expect(getIssueProjectLabel(makeIssue({ id: "tskl-1" }), config)).toBe("kbs");
  });

  it("prefers an explicit label, then the observed prefix", () => {
    const config = makeConfig();
    expect(getIssueProjectLabel(makeIssue({ id: "kbs-1", custom: { project_label: "lbl" } }), config)).toBe("lbl");
    expect(getIssueProjectLabel(makeIssue({ id: "other-1" }), config)).toBe("other");
    expect(getIssueProjectLabel(makeIssue({ id: "kbs-1" }), config)).toBe("kbs");
  });

  it("uses the project key for ids without a prefix", () => {
    expect(getIssueProjectLabel(makeIssue({ id: "plain" }), makeConfig())).toBe("kbs");
  });
});

describe("collectDescendants", () => {
  it("collects the parent and all nested children", () => {
    const issues = [
      makeIssue({ id: "a" }),
      makeIssue({ id: "b", parent: "a" }),
      makeIssue({ id: "c", parent: "b" }),
      makeIssue({ id: "d" })
    ];
    expect(collectDescendants(issues, "a")).toEqual(new Set(["a", "b", "c"]));
  });

  it("terminates on cycles", () => {
    const issues = [makeIssue({ id: "a", parent: "b" }), makeIssue({ id: "b", parent: "a" })];
    expect(collectDescendants(issues, "a")).toEqual(new Set(["a", "b"]));
  });
});

describe("buildPriorityLookup", () => {
  it("maps numeric priorities to names", () => {
    expect(buildPriorityLookup(makeConfig())).toEqual({ 1: "high", 2: "medium" });
  });
});

describe("view mode helpers", () => {
  it("resolves the board type filter", () => {
    expect(resolveBoardTypeFilter(true, "epics")).toBe("all");
    expect(resolveBoardTypeFilter(false, "epics")).toBe("epics");
    expect(resolveBoardTypeFilter(false, null)).toBe("issues");
  });

  it("counts issues per view mode and excludes sub-tasks", () => {
    const counts = computeViewModeCounts([
      makeIssue({ id: "1", type: "initiative" }),
      makeIssue({ id: "2", type: "epic" }),
      makeIssue({ id: "3", type: "epic" }),
      makeIssue({ id: "4", type: "task" }),
      makeIssue({ id: "5", type: "sub-task" })
    ]);
    expect(counts).toEqual({ initiatives: 1, epics: 2, issues: 1 });
  });

  it("selects the first non empty view mode", () => {
    expect(selectNonEmptyViewMode({ initiatives: 1, epics: 1, issues: 1 })).toBe("initiatives");
    expect(selectNonEmptyViewMode({ initiatives: 0, epics: 1, issues: 1 })).toBe("epics");
    expect(selectNonEmptyViewMode({ initiatives: 0, epics: 0, issues: 0 })).toBe("issues");
  });
});

describe("resolveRouteContext", () => {
  const epic = makeIssue({ id: "kbs-epic01", type: "epic" });
  const child = makeIssue({ id: "kbs-child1", parent: "kbs-epic01" });
  const stranger = makeIssue({ id: "kbs-other1" });
  const task = makeIssue({ id: "kbs-task01", type: "task" });
  const snapshot = makeSnapshot([epic, child, stranger, task]);

  it("returns the route error when there is no base path", () => {
    const result = resolveRouteContext(makeRoute({ basePath: null, error: "bad" }), snapshot, "epics");
    expect(result).toEqual({ viewMode: null, selectedIssue: null, parentIssue: null, error: "bad" });
  });

  it("falls back to the current view mode without a snapshot", () => {
    expect(resolveRouteContext(makeRoute(), null, "issues").viewMode).toBe("issues");
    expect(resolveRouteContext(makeRoute({ viewMode: "epics" }), null, "issues").viewMode).toBe("epics");
  });

  it("returns a route view mode directly", () => {
    expect(resolveRouteContext(makeRoute({ viewMode: "epics" }), snapshot, "issues").viewMode).toBe("epics");
  });

  it("derives the view mode from the selected issue type", () => {
    const result = resolveRouteContext(makeRoute({ issueId: "kbs-epic01" }), snapshot, null);
    expect(result.viewMode).toBe("epics");
    expect(result.selectedIssue?.id).toBe("kbs-epic01");
    expect(resolveRouteContext(makeRoute({ issueId: "kbs-task01" }), snapshot, null).viewMode).toBe("issues");
  });

  it("reports unknown issues", () => {
    expect(resolveRouteContext(makeRoute({ issueId: "kbs-nope" }), snapshot, null).error).toBe(
      "Issue not found for URL id"
    );
  });

  it("scopes to a parent and accepts descendants", () => {
    const result = resolveRouteContext(makeRoute({ parentId: "kbs-epic01", issueId: "kbs-child1" }), snapshot, null);
    expect(result.parentIssue?.id).toBe("kbs-epic01");
    expect(result.selectedIssue?.id).toBe("kbs-child1");
    expect(result.error).toBeNull();
  });

  it("rejects selections outside the parent", () => {
    const result = resolveRouteContext(makeRoute({ parentId: "kbs-epic01", issueId: "kbs-other1" }), snapshot, null);
    expect(result.error).toBe("Selected issue is not a descendant of the context parent");
  });

  it("rejects parents that are not initiatives or epics", () => {
    const result = resolveRouteContext(makeRoute({ parentId: "kbs-task01" }), snapshot, null);
    expect(result.error).toBe("Context parent must be an initiative or epic");
  });

  it("keeps the current view mode when nothing is selected", () => {
    expect(resolveRouteContext(makeRoute(), snapshot, "issues").viewMode).toBe("issues");
  });
});
