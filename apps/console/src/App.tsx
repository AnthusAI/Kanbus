import React, { useCallback, useDeferredValue, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  CheckCheck,
  Filter,
  LayoutGrid,
  Lightbulb,
  ListChecks,
  SquareCheckBig,
  Layers
} from "lucide-react";
import { AppShell } from "./components/AppShell";
import { Board, TaskDetailPanel, AnimatedSelector, type SelectorOption } from "@kanbus/ui";
import { ErrorStatusDisplay } from "./components/ErrorStatusDisplay";
import { FilterSidebar } from "./components/FilterSidebar";
import { SettingsPanel } from "./components/SettingsPanel";
import { SearchInput } from "./components/SearchInput";
import { MetricsPanel } from "./components/MetricsPanel";
import {
  fetchSnapshot,
  subscribeToSnapshots,
  subscribeToNotifications,
  type NotificationEvent,
  type UiControlAction,
} from "./api/client";
import { installConsoleTelemetry } from "./utils/console-telemetry";
import { matchesSearchQuery } from "./utils/issue-search";
import type { Issue, IssuesSnapshot, ProjectConfig } from "./types/issues";
import { useAppearance } from "./hooks/useAppearance";

type ViewMode = "initiatives" | "epics" | "issues";
type PanelMode = "board" | "metrics";
type NavAction = "push" | "pop" | "none";
type RouteContext = {
  account: string | null;
  project: string | null;
  basePath: string | null;
  viewMode: ViewMode | null;
  issueId: string | null;
  parentId: string | null;
  search: string | null;
  focused: string | null;
  comment: string | null;
  typeFilter: string | null;
  error: string | null;
};
type IssueSelectionContext = {
  viewMode: ViewMode | null;
  selectedIssue: Issue | null;
  parentIssue: Issue | null;
  error: string | null;
};

const VIEW_MODE_STORAGE_KEY = "kanbus.console.viewMode";
const DETAIL_WIDTH_STORAGE_KEY = "kanbus.console.detailWidth";
const ENABLED_PROJECTS_STORAGE_KEY = "kanbus.console.enabledProjects";
const SHOW_LOCAL_STORAGE_KEY = "kanbus.console.showLocal";
const SHOW_SHARED_STORAGE_KEY = "kanbus.console.showShared";
const SHOW_TYPE_FILTER_TOOLBAR_KEY = "kanbus.console.showTypeFilterToolbar";
const SHOW_INITIATIVES_IN_TYPE_FILTER_KEY = "kanbus.console.showInitiativesInTypeFilter";
const PANEL_MODE_STORAGE_KEY = "kanbus.console.panelMode";

function loadStoredEnabledProjects(): Set<string> | null {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(ENABLED_PROJECTS_STORAGE_KEY);
  if (!stored) {
    return null;
  }
  try {
    const parsed = JSON.parse(stored);
    if (Array.isArray(parsed)) {
      return new Set(parsed);
    }
  } catch {
    // ignore
  }
  return null;
}

function loadStoredBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") {
    return fallback;
  }
  const stored = window.localStorage.getItem(key);
  if (stored === "false") {
    return false;
  }
  return fallback;
}

function loadStoredViewMode(): ViewMode {
  if (typeof window === "undefined") {
    return "epics";
  }
  const stored = window.localStorage.getItem(VIEW_MODE_STORAGE_KEY);
  if (stored === "initiatives" || stored === "epics" || stored === "issues") {
    return stored;
  }
  if (stored === "tasks") {
    return "issues";
  }
  return "epics";
}

function loadStoredPanelMode(): PanelMode {
  if (typeof window === "undefined") {
    return "board";
  }
  const stored = window.localStorage.getItem(PANEL_MODE_STORAGE_KEY);
  if (stored === "metrics") {
    return "metrics";
  }
  return "board";
}

function loadStoredDetailWidth(): number {
  if (typeof window === "undefined") {
    return 33;
  }
  const stored = window.localStorage.getItem(DETAIL_WIDTH_STORAGE_KEY);
  const parsed = stored ? Number.parseFloat(stored) : NaN;
  if (Number.isFinite(parsed) && parsed >= 20 && parsed <= 60) {
    return parsed;
  }
  return 33;
}

function parseQueryParams(search: string): {
  search: string | null;
  focused: string | null;
  comment: string | null;
  typeFilter: string | null;
} {
  const params = new URLSearchParams(search);
  const searchParam = params.get("search");
  const focusedParam = params.get("focused");
  const commentParam = params.get("comment");
  const typeParam = params.get("type");
  return {
    search: searchParam && searchParam.length > 0 ? searchParam : null,
    focused: focusedParam && focusedParam.length > 0 ? focusedParam : null,
    comment: commentParam && commentParam.length > 0 ? commentParam : null,
    typeFilter: typeParam === "all" ? "all" : null,
  };
}

function parseRoute(pathname: string, queryString?: string): RouteContext {
  const qp = parseQueryParams(queryString ?? window.location.search);
  const segments = pathname.split("/").filter(Boolean);
  if (segments[segments.length - 1] === "index.html") {
    segments.pop();
  }
  const viewModes: ViewMode[] = ["initiatives", "epics", "issues"];
  const isLocal =
    segments.length === 0 || (segments[0] && viewModes.includes(segments[0] as ViewMode));
  if (isLocal) {
    const rest = segments;
    if (rest.length === 0) {
      return {
        account: null,
        project: null,
        basePath: "",
        viewMode: loadStoredViewMode(),
        issueId: null,
        parentId: null,
        ...qp,
        error: null
      };
    }
    const head = rest[0];
    if (head === "initiatives" || head === "epics" || head === "issues") {
      if (rest.length === 1) {
        return {
          account: null,
          project: null,
          basePath: "",
          viewMode: head,
          issueId: null,
          parentId: null,
          ...qp,
          error: null
        };
      }
    }
    if (head === "issues") {
      if (rest.length === 2) {
        return {
          account: null,
          project: null,
          basePath: "",
          viewMode: null,
          issueId: rest[1],
          parentId: null,
          ...qp,
          error: null
        };
      }
      if (rest.length === 3 && rest[2] === "all") {
        return {
          account: null,
          project: null,
          basePath: "",
          viewMode: null,
          issueId: null,
          parentId: rest[1],
          ...qp,
          error: null
        };
      }
      if (rest.length === 3) {
        return {
          account: null,
          project: null,
          basePath: "",
          viewMode: null,
          issueId: rest[2],
          parentId: rest[1],
          ...qp,
          error: null
        };
      }
    }
    return {
      account: null,
      project: null,
      basePath: "",
      viewMode: null,
      issueId: null,
      parentId: null,
      search: null,
      focused: null,
      comment: null,
      typeFilter: null,
      error: "Unsupported console route"
    };
  }
  if (segments.length < 2) {
    return {
      account: null,
      project: null,
      basePath: null,
      viewMode: null,
      issueId: null,
      parentId: null,
      search: null,
      focused: null,
      comment: null,
      typeFilter: null,
      error: "URL must include /:account/:project"
    };
  }
  const account = segments[0];
  const project = segments[1];
  const basePath = `/${account}/${project}`;
  const rest = segments.slice(2);
  if (rest.length === 0) {
    return {
      account,
      project,
      basePath,
      viewMode: loadStoredViewMode(),
      issueId: null,
      parentId: null,
      ...qp,
      error: null
    };
  }
  const head = rest[0];
  if (head === "initiatives" || head === "epics" || head === "issues") {
    if (rest.length === 1) {
      return {
        account,
        project,
        basePath,
        viewMode: head,
        issueId: null,
        parentId: null,
        ...qp,
        error: null
      };
    }
  }
  if (head === "issues") {
    if (rest.length === 2) {
      return {
        account,
        project,
        basePath,
        viewMode: null,
        issueId: rest[1],
        parentId: null,
        ...qp,
        error: null
      };
    }
    if (rest.length === 3 && rest[2] === "all") {
      return {
        account,
        project,
        basePath,
        viewMode: null,
        issueId: null,
        parentId: rest[1],
        ...qp,
        error: null
      };
    }
    if (rest.length === 3) {
      return {
        account,
        project,
        basePath,
        viewMode: null,
        issueId: rest[2],
        parentId: rest[1],
        ...qp,
        error: null
      };
    }
  }
  return {
    account,
    project,
    basePath,
    viewMode: null,
    issueId: null,
    parentId: null,
    search: null,
    focused: null,
    comment: null,
    typeFilter: null,
    error: "Unsupported console route"
  };
}

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

function resolveIssueByIdentifier(
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

function getIssueProjectLabel(issue: Issue, config: ProjectConfig | null): string {
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

function collectDescendants(issues: Issue[], parentId: string): Set<string> {
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

function buildUrl(
  path: string,
  params: {
    search?: string | null;
    focused?: string | null;
    comment?: string | null;
    typeFilter?: string | null;
  } = {}
): string {
  const qp = new URLSearchParams();
  if (params.focused) {
    qp.set("focused", params.focused);
  }
  if (params.search) {
    qp.set("search", params.search);
  }
  if (params.comment) {
    qp.set("comment", params.comment);
  }
  if (params.typeFilter === "all") {
    qp.set("type", "all");
  }
  const qs = qp.toString();
  return qs ? `${path}?${qs}` : path;
}

function navigate(
  path: string,
  setRoute: (route: RouteContext) => void,
  navActionRef?: React.MutableRefObject<NavAction>
) {
  const url = new URL(path, window.location.href);
  window.history.pushState({}, "", url.pathname + url.search);
  if (navActionRef) {
    navActionRef.current = "push";
  }
  setRoute(parseRoute(url.pathname, url.search));
}

function buildPriorityLookup(config: ProjectConfig): Record<number, string> {
  return Object.entries(config.priorities).reduce<Record<number, string>>(
    (accumulator, [key, value]) => {
      accumulator[Number(key)] = value.name;
      return accumulator;
    },
    {}
  );
}

function getStatusColumns(config: ProjectConfig): string[] {
  return config.statuses.map((s) => s.key);
}

function getInitialCollapsedColumns(config: ProjectConfig): Set<string> {
  return new Set(
    config.statuses.filter((s) => s.collapsed).map((s) => s.key)
  );
}

const VIEW_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  initiatives: Lightbulb,
  epics: ListChecks,
  issues: SquareCheckBig,
  "sub-tasks": CheckCheck
};

function computeViewModeCounts(issues: Issue[]): Record<ViewMode, number> {
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

function selectNonEmptyViewMode(counts: Record<ViewMode, number>): ViewMode {
  if (counts.initiatives > 0) {
    return "initiatives";
  }
  if (counts.epics > 0) {
    return "epics";
  }
  return "issues";
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4">
      <path
        fill="currentColor"
        d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.06-.94l2.03-1.58a.5.5 0 0 0 .12-.63l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.35 7.35 0 0 0-1.63-.94l-.36-2.54a.5.5 0 0 0-.5-.42h-3.84a.5.5 0 0 0-.5.42l-.36 2.54c-.58.24-1.13.55-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.7 8.85a.5.5 0 0 0 .12.63l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58a.5.5 0 0 0-.12.63l1.92 3.32a.5.5 0 0 0 .6.22l2.39-.96c.5.39 1.05.7 1.63.94l.36 2.54a.5.5 0 0 0 .5.42h3.84a.5.5 0 0 0 .5-.42l.36-2.54c.58-.24 1.13-.55 1.63-.94l2.39.96a.5.5 0 0 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.63l-2.03-1.58zM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5z"
      />
    </svg>
  );
}

export default function App() {
  const [snapshot, setSnapshot] = useState<IssuesSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorTime, setErrorTime] = useState<number | null>(null);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode | null>(() =>
    loadStoredViewMode()
  );
  const [panelMode, setPanelMode] = useState<PanelMode>(() =>
    loadStoredPanelMode()
  );
  const [loadingVisible, setLoadingVisible] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Issue | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [activeSidebar, setActiveSidebar] = useState<"filter" | "settings" | null>(null);
  const [collapsedColumns, setCollapsedColumns] = useState<Set<string>>(new Set());
  const [isResizing, setIsResizing] = useState(false);
  const [detailWidth, setDetailWidth] = useState(() => loadStoredDetailWidth());
  const [detailMaximized, setDetailMaximized] = useState(false);
  const [route, setRoute] = useState<RouteContext>(() =>
    parseRoute(window.location.pathname, window.location.search)
  );
  const [focusedIssueId, setFocusedIssueId] = useState<string | null>(() => {
    const initial = parseRoute(window.location.pathname, window.location.search);
    return initial.focused ?? null;
  });
  const [focusedCommentId, setFocusedCommentId] = useState<string | null>(() => {
    const initial = parseRoute(window.location.pathname, window.location.search);
    return initial.comment ?? null;
  });
  const [searchQuery, setSearchQuery] = useState<string>(() => {
    const initial = parseRoute(window.location.pathname, window.location.search);
    return initial.search ?? "";
  });
  const [detailClosing, setDetailClosing] = useState(false);
  const [detailNavDirection, setDetailNavDirection] = useState<NavAction>("none");
  const [enabledProjects, setEnabledProjects] = useState<Set<string> | null>(() => loadStoredEnabledProjects());
  const [showLocal, setShowLocal] = useState(() => loadStoredBoolean(SHOW_LOCAL_STORAGE_KEY, true));
  const [showShared, setShowShared] = useState(() => loadStoredBoolean(SHOW_SHARED_STORAGE_KEY, true));
  const [showTypeFilterToolbar, setShowTypeFilterToolbar] = useState(() =>
    loadStoredBoolean(SHOW_TYPE_FILTER_TOOLBAR_KEY, true)
  );
  const [showInitiativesInTypeFilter, setShowInitiativesInTypeFilter] = useState(() =>
    loadStoredBoolean(SHOW_INITIATIVES_IN_TYPE_FILTER_KEY, true)
  );
  const layoutFrameRef = React.useRef<HTMLDivElement | null>(null);
  const navActionRef = React.useRef<NavAction>("none");
  const wasDetailOpenRef = React.useRef(false);
  const collapsedColumnsInitialized = React.useRef(false);
  const viewModeAutoCorrected = React.useRef(false);
  const lastTypeSelectionRef = React.useRef<string | null>(null);
  useAppearance();
  const config = snapshot?.config;
  const issues = useMemo(() => {
    const list = snapshot?.issues ?? [];
    if (!list.length) return [];
    const map = new Map<string, Issue>();
    list.forEach((issue) => {
      if (issue?.id) {
        map.set(issue.id, issue);
      }
    });
    return Array.from(map.values());
  }, [snapshot?.issues]);
  const deferredIssues = useDeferredValue(issues);
  const apiBase = route.basePath != null ? `${route.basePath}/api` : "";
  const refreshSnapshot = useCallback(() => {
    if (!apiBase) {
      return;
    }
    fetchSnapshot(apiBase)
      .then((data) => setSnapshot(data))
      .catch((err) => console.warn("[snapshot] refresh failed", err));
  }, [apiBase]);
  const showAllTypes = route.typeFilter === "all";

  // Initialize collapsed columns from config (only once)
  useEffect(() => {
    if (config && !collapsedColumnsInitialized.current) {
      setCollapsedColumns(getInitialCollapsedColumns(config));
      collapsedColumnsInitialized.current = true;
    }
  }, [config]);

  useEffect(() => {
    const handlePop = () => {
      navActionRef.current = "pop";
      setRoute(parseRoute(window.location.pathname, window.location.search));
    };
    window.addEventListener("popstate", handlePop);
    return () => window.removeEventListener("popstate", handlePop);
  }, []);

  useEffect(() => {
    const parsed = parseRoute(window.location.pathname, window.location.search);
    if (
      parsed.basePath !== route.basePath
      || parsed.issueId !== route.issueId
      || parsed.parentId !== route.parentId
      || parsed.viewMode !== route.viewMode
      || parsed.search !== route.search
      || parsed.focused !== route.focused
      || parsed.comment !== route.comment
      || parsed.typeFilter !== route.typeFilter
      || parsed.error !== route.error
    ) {
      setRoute(parsed);
    }
  }, [route]);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    if (route.basePath == null) {
      setError("URL must include /:account/:project");
      setLoading(false);
      return () => {};
    }
    const apiBase = `${route.basePath}/api`;
    installConsoleTelemetry(apiBase);
    fetchSnapshot(apiBase)
      .then((data) => {
        if (isMounted) {
          setSnapshot(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (isMounted) {
          const errorMessage = err instanceof Error ? err.message : "Failed to load data";
          setError(errorMessage);
          setErrorTime(Date.now());
        }
      })
      .finally(() => {
        if (isMounted) {
          setLoading(false);
        }
      });

    const unsubscribe = subscribeToSnapshots(
      apiBase,
      (data) => {
        setSnapshot(data);
        setError(null);
        setErrorTime(null);
      },
      () => {
        setError("SSE connection issue. Attempting to reconnect.");
        setErrorTime(Date.now());
      }
    );

    return () => {
      isMounted = false;
      unsubscribe();
    };
  }, [route.basePath]);

  // Real-time notification subscription
  useEffect(() => {
    const apiBase = `${route.basePath}/api`;
    const unsubscribe = subscribeToNotifications(
      apiBase,
      (event: NotificationEvent) => {
        switch (event.type) {
          case "issue_focused":
            setFocusedIssueId(event.issue_id);
            setFocusedCommentId(event.comment_id ?? null);
            break;
          case "issue_created":
          case "issue_updated":
            // Use the issue data from the notification payload directly
            if (event.issue_data && snapshot) {
              const updatedIssues = snapshot.issues.map(issue =>
                issue.id === event.issue_id ? event.issue_data : issue
              );
              // If this is a new issue (created), add it if not already present in updatedIssues
              if (event.type === "issue_created" && !updatedIssues.find(i => i.id === event.issue_id)) {
                updatedIssues.push(event.issue_data);
              }
              setSnapshot({
                ...snapshot,
                issues: updatedIssues,
                updated_at: new Date().toISOString()
              });
              console.info("[notifications] applied issue update immediately", {
                type: event.type,
                issueId: event.issue_id
              });
            } else {
              // Fallback to fetching if no snapshot yet
              fetchSnapshot(apiBase).then(setSnapshot).catch(console.error);
            }
            break;
          case "issue_deleted":
            // Remove the deleted issue from snapshot
            if (snapshot) {
              setSnapshot({
                ...snapshot,
                issues: snapshot.issues.filter(issue => issue.id !== event.issue_id),
                updated_at: new Date().toISOString()
              });
              console.info("[notifications] applied issue deletion immediately", { issueId: event.issue_id });
            } else {
              fetchSnapshot(apiBase).then(setSnapshot).catch(console.error);
            }
            break;
          case "ui_control":
            handleUiControlAction(event.action);
            break;
        }
      },
      (error) => {
        console.warn("[notifications] connection error", error);
      }
    );

    return () => {
      unsubscribe();
    };
  }, [route.basePath]);

  // Auto-select focused issue in detail panel and encode focus in URL
  useEffect(() => {
    if (!focusedIssueId || !snapshot) {
      return;
    }
    const projectKey = snapshot.config.project_key;
    const resolved = resolveIssueByIdentifier(snapshot.issues, focusedIssueId, projectKey);
    if (resolved.issue) {
      const issueUrl = buildUrl(
        `${route.basePath}/issues/${resolved.issue.id}`,
        {
          focused: resolved.issue.id,
          search: searchQuery || null,
          comment: focusedCommentId,
          typeFilter: route.typeFilter
        }
      );
      navigate(issueUrl, setRoute, navActionRef);
    }
  }, [focusedIssueId, focusedCommentId, snapshot, route.basePath]);

  // Sync searchQuery, focusedIssueId, and focusedCommentId from URL on browser back/forward navigation
  useEffect(() => {
    if (route.search !== null && route.search !== searchQuery) {
      setSearchQuery(route.search);
    } else if (route.search === null && searchQuery) {
      setSearchQuery("");
    }
    if (route.focused !== null && route.focused !== focusedIssueId) {
      setFocusedIssueId(route.focused);
    } else if (route.focused === null && focusedIssueId) {
      setFocusedIssueId(null);
    }
    if (route.comment !== null && route.comment !== focusedCommentId) {
      setFocusedCommentId(route.comment);
    } else if (route.comment === null && focusedCommentId) {
      setFocusedCommentId(null);
    }
  }, [route.search, route.focused, route.comment]);

  useEffect(() => {
    if (!viewMode) {
      return;
    }
    window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode);
  }, [viewMode]);

  useEffect(() => {
    window.localStorage.setItem(PANEL_MODE_STORAGE_KEY, panelMode);
  }, [panelMode]);

  useEffect(() => {
    if (!snapshot) {
      return;
    }
    // Reset auto-correction flag on new snapshot to allow re-evaluation
    viewModeAutoCorrected.current = false;

    if (route.viewMode) {
      return;
    }
    if (showAllTypes) {
      return;
    }
    if (route.parentId || focusedIssueId || searchQuery.trim()) {
      return;
    }
    if (!viewMode) {
      return;
    }

    const counts = computeViewModeCounts(snapshot.issues);
    const preferred = selectNonEmptyViewMode(counts);
    if (counts[viewMode] === 0 && counts[preferred] > 0) {
      viewModeAutoCorrected.current = true;
      setViewMode(preferred);
      if (route.basePath != null) {
        navigate(`${route.basePath}/${preferred}/`, setRoute, navActionRef);
      }
    } else {
      viewModeAutoCorrected.current = true;
    }
  }, [snapshot, focusedIssueId, route.basePath, route.parentId, route.viewMode, searchQuery, viewMode, showAllTypes]);

  useEffect(() => {
    if (route.viewMode) {
      setViewMode(route.viewMode);
      return;
    }
    if (route.parentId) {
      setViewMode(null);
    }
    if (!route.parentId && !route.issueId) {
      const path = window.location.pathname;
      if (path.endsWith("/issues") || path.endsWith("/issues/")) {
        setViewMode("issues");
      }
    }
  }, [route.parentId, route.viewMode]);

  useEffect(() => {
    window.localStorage.setItem(DETAIL_WIDTH_STORAGE_KEY, String(detailWidth));
  }, [detailWidth]);

  useEffect(() => {
    if (enabledProjects != null) {
      window.localStorage.setItem(ENABLED_PROJECTS_STORAGE_KEY, JSON.stringify([...enabledProjects]));
    }
  }, [enabledProjects]);

  useEffect(() => {
    window.localStorage.setItem(SHOW_LOCAL_STORAGE_KEY, String(showLocal));
  }, [showLocal]);

  useEffect(() => {
    window.localStorage.setItem(SHOW_SHARED_STORAGE_KEY, String(showShared));
  }, [showShared]);

  useEffect(() => {
    window.localStorage.setItem(
      SHOW_TYPE_FILTER_TOOLBAR_KEY,
      String(showTypeFilterToolbar)
    );
  }, [showTypeFilterToolbar]);

  useEffect(() => {
    window.localStorage.setItem(
      SHOW_INITIATIVES_IN_TYPE_FILTER_KEY,
      String(showInitiativesInTypeFilter)
    );
  }, [showInitiativesInTypeFilter]);

  useLayoutEffect(() => {
    const frame = layoutFrameRef.current;
    const shell = typeof document !== "undefined"
      ? (document.querySelector(".app-shell") as HTMLElement | null)
      : null;
    if (!frame) {
      return;
    }

    let raf = 0;
    const update = () => {
      const frameRect = frame.getBoundingClientRect();
      const viewportRight = document.documentElement.clientWidth || window.innerWidth;
      const outerPadding = Math.max(0, viewportRight - frameRect.right);
      const sidebar = frame.querySelector(".sidebar-column") as HTMLElement | null;
      const isCompact = window.matchMedia("(max-width: 768px)").matches;
      const defaultWidth =
        Number.parseFloat(getComputedStyle(frame).getPropertyValue("--sidebar-width"))
        || 360;
      const measuredWidth = sidebar?.getBoundingClientRect().width || 0;
      const compactWidth = Math.max(0, frameRect.width - outerPadding * 2);
      const sidebarWidth = isCompact ? compactWidth : (measuredWidth || defaultWidth);
      const gap = outerPadding;
      // Board push keeps a constant gap equal to frame padding.
      // Add a 1px overscan to guarantee the sidebar starts fully offscreen.
      const overscan = 1;
      const push = Math.ceil(sidebarWidth + outerPadding * 2) + overscan;
      frame.style.setProperty("--frame-padding", `${outerPadding}px`);
      frame.style.setProperty("--sidebar-gap", `${gap}px`);
      frame.style.setProperty("--sidebar-push", `${push}px`);
    };
    const schedule = () => {
      if (raf) {
        cancelAnimationFrame(raf);
      }
      raf = requestAnimationFrame(update);
    };

    schedule();
    const resizeObserver = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(schedule)
      : null;
    if (resizeObserver) {
      if (shell) {
        resizeObserver.observe(shell);
      }
      resizeObserver.observe(frame);
    }
    window.addEventListener("resize", schedule);
    return () => {
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      window.removeEventListener("resize", schedule);
      if (raf) {
        cancelAnimationFrame(raf);
      }
    };
  }, []);


  useEffect(() => {
    if (!detailMaximized) {
      return;
    }
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setDetailMaximized(false);
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [detailMaximized]);

  const isDetailOpen = Boolean(selectedTask);
  const isDetailVisible = isDetailOpen || detailClosing;

  useEffect(() => {
    const wasOpen = wasDetailOpenRef.current;
    if (isDetailOpen) {
      setDetailClosing(false);
    } else if (wasOpen) {
      setDetailClosing(true);
    }
    wasDetailOpenRef.current = isDetailOpen;
  }, [isDetailOpen]);

  useEffect(() => {
    const layout = layoutFrameRef.current;
    if (!layout) {
      return;
    }
    const widthValue = detailMaximized ? 100 : detailWidth;
    layout.style.setProperty("--detail-width", `${widthValue}%`);
    layout.style.setProperty("--board-width", `${100 - widthValue}%`);
  }, [detailWidth, detailMaximized]);

  useEffect(() => {
    if (!selectedTask || !snapshot) {
      return;
    }
    // Look up in all issues from snapshot, not just filtered issues
    // This allows the detail panel to show updated data even if the task
    // is filtered out (e.g., closed task when "show closed" is toggled off)
    const updatedTask = snapshot.issues.find((issue) => issue.id === selectedTask.id);
    if (!updatedTask) {
      if (route.basePath != null) {
        const nextMode = viewMode ?? loadStoredViewMode();
        navigate(`${route.basePath}/${nextMode}/`, setRoute);
      } else {
        setSelectedTask(null);
      }
      return;
    }
    if (updatedTask !== selectedTask) {
      setSelectedTask(updatedTask);
    }
  }, [snapshot, route.basePath, selectedTask, viewMode]);

  const priorityLookup = useMemo(() => {
    if (!config) {
      return {};
    }
    return buildPriorityLookup(config);
  }, [config]);
  const columns = useMemo(() => {
    if (!config) {
      return [];
    }
    return getStatusColumns(config);
  }, [config]);
  const columnError =
    config && columns.length === 0
      ? "default workflow is required to render columns"
      : null;

  const routeContext = useMemo<IssueSelectionContext>(() => {
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
  }, [route, snapshot, viewMode]);

  const fallbackViewMode = route.parentId ? null : "issues";
  const resolvedViewMode = route.parentId
    ? null
    : routeContext.viewMode ?? route.viewMode ?? viewMode ?? fallbackViewMode;
  const typeFilterValue = showAllTypes ? "all" : resolvedViewMode;

  useEffect(() => {
    if (showInitiativesInTypeFilter) {
      return;
    }
    if (!snapshot || route.basePath == null) {
      return;
    }
    if (showAllTypes) {
      return;
    }
    if (route.parentId || focusedIssueId || searchQuery.trim()) {
      return;
    }
    if (resolvedViewMode !== "initiatives") {
      return;
    }
    const counts = computeViewModeCounts(snapshot.issues);
    const nextMode = counts.epics > 0 ? "epics" : "issues";
    navigate(`${route.basePath}/${nextMode}/`, setRoute, navActionRef);
  }, [
    showInitiativesInTypeFilter,
    snapshot,
    route.basePath,
    route.parentId,
    focusedIssueId,
    searchQuery,
    resolvedViewMode,
    showAllTypes
  ]);

  useEffect(() => {
    setRouteError(routeContext.error);
    if (routeContext.viewMode !== null) {
      setViewMode(routeContext.viewMode);
    }
    setDetailNavDirection(navActionRef.current);
    navActionRef.current = "none";
    setSelectedTask(routeContext.selectedIssue);
  }, [routeContext]);

  useEffect(() => {
    if (!snapshot || !route.issueId) {
      return;
    }
    const resolved = resolveIssueByIdentifier(
      snapshot.issues,
      route.issueId,
      snapshot.config.project_key
    );
    if (resolved.issue) {
      const type = resolved.issue.type;
      const derivedViewMode =
        type === "initiative" ? "initiatives" : type === "epic" ? "epics" : "issues";
      setViewMode(derivedViewMode);
      setSelectedTask(resolved.issue);
    }
  }, [route.issueId, snapshot]);

  const handleFocus = (issueId: string) => {
    setFocusedIssueId((prev) => prev === issueId ? null : issueId);
    // URL update for focus is handled by the focusedIssueId useEffect above
  };

  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
    if (route.basePath != null) {
      const url = buildUrl(window.location.pathname, {
        search: query || null,
        focused: focusedIssueId,
        typeFilter: route.typeFilter
      });
      const parsed = new URL(url, window.location.href);
      window.history.replaceState({}, "", parsed.pathname + parsed.search);
      setRoute(parseRoute(parsed.pathname, parsed.search));
    }
  };

  const handleSearchClear = () => {
    setSearchQuery("");
    if (route.basePath != null) {
      const url = buildUrl(window.location.pathname, {
        focused: focusedIssueId,
        typeFilter: route.typeFilter
      });
      const parsed = new URL(url, window.location.href);
      window.history.replaceState({}, "", parsed.pathname + parsed.search);
      setRoute(parseRoute(parsed.pathname, parsed.search));
    }
  };

  const handleTypeFilterChange = (value: string) => {
    if (route.basePath == null) {
      return;
    }
    const currentRoute = parseRoute(window.location.pathname, window.location.search);
    const currentShowAll = currentRoute.typeFilter === "all";
    const currentViewMode = currentRoute.parentId
      ? null
      : currentRoute.viewMode ?? viewMode ?? loadStoredViewMode();
    if (value === "all") {
      const url = buildUrl(window.location.pathname, {
        search: searchQuery || null,
        focused: focusedIssueId,
        comment: focusedCommentId,
        typeFilter: "all"
      });
      const parsed = new URL(url, window.location.href);
      window.history.replaceState({}, "", parsed.pathname + parsed.search);
      setRoute(parseRoute(parsed.pathname, parsed.search));
      lastTypeSelectionRef.current = "all";
      return;
    }
    const nextMode = value as ViewMode;
    const repeatClick = lastTypeSelectionRef.current === nextMode;
    if (!currentShowAll && currentViewMode === nextMode) {
      if (repeatClick) {
        const url = buildUrl(window.location.pathname, {
          search: searchQuery || null,
          focused: focusedIssueId,
          comment: focusedCommentId,
          typeFilter: "all"
        });
        const parsed = new URL(url, window.location.href);
        window.history.replaceState({}, "", parsed.pathname + parsed.search);
        setRoute(parseRoute(parsed.pathname, parsed.search));
        lastTypeSelectionRef.current = "all";
        return;
      }
      lastTypeSelectionRef.current = nextMode;
      return;
    }
    lastTypeSelectionRef.current = nextMode;
    const nextUrl = buildUrl(`${route.basePath}/${nextMode}/`, {
      typeFilter: null
    });
    navigate(nextUrl, setRoute, navActionRef);
  };

  const handlePanelModeChange = (value: string) => {
    refreshSnapshot();
    if (value === "metrics") {
      setPanelMode("metrics");
      return;
    }
    setPanelMode("board");
  };

  const handleTaskClose = () => {
    setDetailClosing(true);
    setDetailMaximized(false);
    if (route.basePath == null) {
      setSelectedTask(null);
      return;
    }
    setSelectedTask(null);
    const nextMode = resolvedViewMode ?? loadStoredViewMode();
    const nextUrl = buildUrl(`${route.basePath}/${nextMode}/`, {
      typeFilter: route.typeFilter
    });
    navigate(nextUrl, setRoute, navActionRef);
  };

  const openSidebar = (target: "filter" | "settings") => {
    const switching = sidebarOpen && activeSidebar && activeSidebar !== target;
    if (switching) {
      setExitingSidebar(activeSidebar);
      setSidebarPhase("opening");
    } else {
      setExitingSidebar(null);
    }
    if (target === "filter") {
      setSettingsOpen(false);
      setFilterOpen(true);
    } else {
      setFilterOpen(false);
      setSettingsOpen(true);
    }
    setActiveSidebar(target);
  };

  const closeSidebar = (target: "filter" | "settings") => {
    if (target === "filter") {
      setFilterOpen(false);
    } else {
      setSettingsOpen(false);
    }
  };

  const clearFocus = () => {
    setFocusedIssueId(null);
    setFocusedCommentId(null);
    if (route.basePath != null) {
      const url = buildUrl(window.location.pathname, {
        search: searchQuery || null,
        typeFilter: route.typeFilter
      });
      const parsed = new URL(url, window.location.href);
      window.history.replaceState({}, "", parsed.pathname + parsed.search);
      setRoute(parseRoute(parsed.pathname, parsed.search));
    }
  };

  const handleUiControlAction = (action: UiControlAction) => {
    switch (action.action) {
      case "clear_focus":
        clearFocus();
        break;
      case "set_view_mode":
        if (route.basePath != null) {
          const nextMode = action.mode as ViewMode;
          navigate(`${route.basePath}/${nextMode}/`, setRoute, navActionRef);
        }
        break;
      case "set_search":
        setSearchQuery(action.query);
        if (route.basePath != null) {
          const url = buildUrl(window.location.pathname, {
            search: action.query || null,
            focused: focusedIssueId,
            typeFilter: route.typeFilter
          });
          const parsed = new URL(url, window.location.href);
          window.history.replaceState({}, "", parsed.pathname + parsed.search);
          setRoute(parseRoute(parsed.pathname, parsed.search));
        }
        break;
      case "maximize_detail":
        setDetailMaximized(true);
        break;
      case "restore_detail":
        setDetailMaximized(false);
        break;
      case "close_detail":
        if (selectedTask) {
          handleTaskClose();
        }
        break;
      case "toggle_settings":
        setSettingsOpen((prev) => {
          const next = !prev;
          if (next) {
            setActiveSidebar("settings");
            setFilterOpen(false);
          }
          return next;
        });
        break;
      case "set_setting":
        // Settings are handled by SettingsPanel component
        // This would require exposing a ref or callback to update settings
        console.info("[ui_control] set_setting not yet implemented", action);
        break;
      case "collapse_column":
        setCollapsedColumns((prev) => new Set([...prev, action.column_name]));
        break;
      case "expand_column":
        setCollapsedColumns((prev) => {
          const next = new Set(prev);
          next.delete(action.column_name);
          return next;
        });
        break;
      case "select_issue":
        if (snapshot) {
          const projectKey = snapshot.config.project_key;
          const resolved = resolveIssueByIdentifier(snapshot.issues, action.issue_id, projectKey);
          if (resolved.issue) {
            const issueUrl = buildUrl(`${route.basePath}/issues/${resolved.issue.id}`, {
              typeFilter: route.typeFilter
            });
            navigate(issueUrl, setRoute, navActionRef);
          }
        }
        break;
      case "reload_page":
        console.info("[ui_control] reloading page");
        window.location.reload();
        break;
    }
  };

  const typeFilterOptions = useMemo(() => {
    const buildOption = (
      id: string,
      label: string,
      icon: React.ComponentType<{ className?: string }>
    ): SelectorOption => ({
      id,
      label,
      content: (
        <span className="selector-option">
          {React.createElement(icon, { className: "h-4 w-4" })}
          <span className="selector-label">{label}</span>
        </span>
      )
    });
    const options: SelectorOption[] = [];
    options.push(buildOption("all", "All", Layers));
    if (showInitiativesInTypeFilter) {
      options.push(buildOption("initiatives", "Initiatives", VIEW_ICONS.initiatives));
    }
    options.push(buildOption("epics", "Epics", VIEW_ICONS.epics));
    options.push(buildOption("issues", "Issues", VIEW_ICONS.issues));
    return options;
  }, [showInitiativesInTypeFilter]);

  const panelModeOptions = useMemo(() => {
    const buildOption = (
      id: string,
      label: string,
      icon: React.ComponentType<{ className?: string }>
    ): SelectorOption => ({
      id,
      label,
      content: (
        <span className="selector-option">
          {React.createElement(icon, { className: "h-4 w-4" })}
          <span className="selector-label">{label}</span>
        </span>
      )
    });
    return [
      buildOption("board", "Board", LayoutGrid),
      buildOption("metrics", "Metrics", BarChart3)
    ];
  }, [panelMode]);

  const projectLabels = useMemo(() => {
    if (!config) {
      return [];
    }
    const labels = new Set<string>();
    if (config.project_key) {
      labels.add(config.project_key);
    }
    Object.keys(config.virtual_projects ?? {}).forEach((key) => labels.add(key));
    return Array.from(labels);
  }, [config]);
  const hasVirtualProjects = config
    ? Object.keys(config.virtual_projects ?? {}).length > 0
    : false;

  // Ensure project filter state is initialized once config/project labels are known
  useEffect(() => {
    if (projectLabels.length > 0 && enabledProjects === null) {
      setEnabledProjects(new Set(projectLabels));
    }
  }, [projectLabels, enabledProjects]);

  // Track project labels to auto-enable any newly discovered projects (e.g., virtual projects added at runtime)
  const prevProjectLabelsRef = React.useRef<Set<string>>(new Set());
  useEffect(() => {
    if (projectLabels.length === 0) {
      return;
    }
    const prev = prevProjectLabelsRef.current;
    const nextLabels = new Set(projectLabels);
    const newlyAdded = projectLabels.filter((label) => !prev.has(label));

    if (!enabledProjects || enabledProjects.size === 0) {
      setEnabledProjects(new Set(projectLabels));
    } else if (newlyAdded.length > 0) {
      setEnabledProjects((prevEnabled) => {
        const base = prevEnabled ? new Set(prevEnabled) : new Set<string>();
        newlyAdded.forEach((label) => base.add(label));
        return base;
      });
    }

    prevProjectLabelsRef.current = nextLabels;
  }, [projectLabels, enabledProjects]);

  const effectiveEnabledProjects = useMemo(() => {
    if (enabledProjects != null) {
      return enabledProjects;
    }
    return new Set(projectLabels);
  }, [enabledProjects, projectLabels]);

  const handleToggleProject = (label: string) => {
    setEnabledProjects((prev) => {
      const current = prev ?? new Set(projectLabels);
      const next = new Set(current);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  const hasLocalIssues = useMemo(() => {
    return issues.some((issue) => issue.custom?.source === "local");
  }, [issues]);

  const focusedIssueLabel = useMemo(() => {
    if (!focusedIssueId) {
      return null;
    }
    if (!snapshot) {
      return focusedIssueId;
    }
    const resolved = resolveIssueByIdentifier(
      snapshot.issues,
      focusedIssueId,
      snapshot.config.project_key
    );
    return resolved.issue?.title ?? focusedIssueId;
  }, [snapshot, focusedIssueId]);

  const filteredIssues = useMemo(() => {
    // Use user-selected projects; fall back to all labels if none selected yet
    const projectFilterSet = enabledProjects ?? new Set(projectLabels);
    // Use non-deferred issues when search is active for immediate feedback
    const sourceIssues = issues;
    let result = sourceIssues;
    const hasSearchQuery = searchQuery.trim().length > 0;

    if (focusedIssueId) {
      const ids = collectDescendants(sourceIssues, focusedIssueId);
      result = sourceIssues.filter((issue) => ids.has(issue.id));
      // When focused, show the entire descendant tree regardless of view mode
      // Don't apply view mode filtering here
    } else if (routeContext.parentIssue) {
      const ids = collectDescendants(sourceIssues, routeContext.parentIssue.id);
      result = sourceIssues.filter((issue) => ids.has(issue.id));
    } else if (route.parentId) {
      result = [];
    } else if (hasSearchQuery) {
      // Global search: search across ALL issues regardless of view mode
      // This implements the Gherkin spec in tskl-dvi.1
      result = sourceIssues;
    } else if (showAllTypes) {
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

    // Apply search filter
    if (hasSearchQuery) {
      result = result.filter((issue) => matchesSearchQuery(issue, searchQuery));
    }

    // Apply project filter
    if (projectLabels.length > 0) {
      result = result.filter((issue) => {
        const label = getIssueProjectLabel(issue, config ?? null);
        return projectFilterSet.has(label);
      });
    }

    // Apply local/shared source filter
    if (!showLocal) {
      result = result.filter((issue) => issue.custom?.source !== "local");
    }
    if (!showShared) {
      result = result.filter((issue) => issue.custom?.source !== "shared");
    }

    return result;
  }, [issues, deferredIssues, resolvedViewMode, routeContext.parentIssue, route.parentId, focusedIssueId, searchQuery, enabledProjects, projectLabels.length, showLocal, showShared, showAllTypes, config]);

  const metricsIssues = useMemo(() => {
    if (!config) {
      return [];
    }
    const projectFilterSet = effectiveEnabledProjects ?? new Set(projectLabels);
    if (typeof window !== "undefined") {
      console.info("[metrics-debug]", {
        labels: projectLabels,
        enabled: Array.from(projectFilterSet)
      });
    }
    const sourceIssues = issues;
    let result = sourceIssues;
    const hasSearchQuery = searchQuery.trim().length > 0;
    if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
      console.info("[metrics] filter projects", Array.from(projectFilterSet), "issues", sourceIssues.length);
    }

    if (focusedIssueId) {
      const ids = collectDescendants(sourceIssues, focusedIssueId);
      result = sourceIssues.filter((issue) => ids.has(issue.id));
    } else if (routeContext.parentIssue) {
      const ids = collectDescendants(sourceIssues, routeContext.parentIssue.id);
      result = sourceIssues.filter((issue) => ids.has(issue.id));
    } else if (route.parentId) {
      result = [];
    } else if (hasSearchQuery) {
      result = sourceIssues;
    }

    if (hasSearchQuery) {
      result = result.filter((issue) => matchesSearchQuery(issue, searchQuery));
    }

    // Always apply project filter when project labels exist (enabledProjects defaults to all)
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
  }, [config, issues, routeContext.parentIssue, route.parentId, focusedIssueId, searchQuery, effectiveEnabledProjects, projectLabels.length, showLocal, showShared]);

  const handleSelectIssue = (issue: Issue) => {
    if (route.basePath == null) {
      return;
    }
    if (route.parentId) {
      const url = buildUrl(`${route.basePath}/issues/${route.parentId}/${issue.id}`, {
        typeFilter: route.typeFilter
      });
      navigate(url, setRoute, navActionRef);
      return;
    }
    const url = buildUrl(`${route.basePath}/issues/${issue.id}`, {
      typeFilter: route.typeFilter
    });
    navigate(url, setRoute, navActionRef);
  };

  const motionMode = typeof document !== "undefined" ? document.documentElement.dataset.motion : "full";
  const toggleMotionClass =
    motionMode === "off"
      ? ""
      : motionMode === "reduced"
      ? "transition-opacity duration-150"
      : "transition-opacity duration-300";

  const transitionKey = `${resolvedViewMode ?? "none"}-${snapshot?.updated_at ?? ""}`;
  const showLoadingIndicator =
    loading || !snapshot;
  const sidebarOpen = filterOpen || settingsOpen;
  const [sidebarReady, setSidebarReady] = useState(false);
  const [sidebarPhase, setSidebarPhase] = useState<"closed" | "opening" | "open" | "closing">("closed");
  const [exitingSidebar, setExitingSidebar] = useState<"filter" | "settings" | null>(null);

  useEffect(() => {
    const id = window.requestAnimationFrame(() => setSidebarReady(true));
    return () => window.cancelAnimationFrame(id);
  }, []);

  useEffect(() => {
    if (filterOpen) {
      setActiveSidebar("filter");
    } else if (settingsOpen) {
      setActiveSidebar("settings");
    }
  }, [filterOpen, settingsOpen]);

  useEffect(() => {
    if (sidebarOpen) {
      setSidebarPhase((prev) => (prev === "open" || prev === "opening" ? prev : "opening"));
      return;
    }
    setSidebarPhase((prev) => (prev === "closed" ? prev : "closing"));
  }, [sidebarOpen]);

  useEffect(() => {
    if (sidebarPhase !== "opening") {
      return;
    }
    const id = window.requestAnimationFrame(() => setSidebarPhase("open"));
    return () => window.cancelAnimationFrame(id);
  }, [sidebarPhase]);

  const handleSidebarTransitionEnd = (
    event: React.TransitionEvent<HTMLDivElement>
  ) => {
    if (event.propertyName !== "transform") {
      return;
    }
    if (event.target !== event.currentTarget) {
      return;
    }
    if (!sidebarOpen && sidebarPhase === "closing") {
      setSidebarPhase("closed");
      setActiveSidebar(null);
      setExitingSidebar(null);
      return;
    }
    const target = event.currentTarget as HTMLElement;
    const testId = target.dataset.testid;
    if (testId && exitingSidebar && testId.includes(exitingSidebar)) {
      setExitingSidebar(null);
    }
  };

  useEffect(() => {
    if (showLoadingIndicator) {
      setLoadingVisible(true);
    }
  }, [showLoadingIndicator]);

  useEffect(() => {
    if (showLoadingIndicator) {
      return;
    }
    const timer = window.setTimeout(() => {
      setLoadingVisible(false);
    }, 350);
    return () => window.clearTimeout(timer);
  }, [showLoadingIndicator]);

  return (
    <AppShell>
      <div className="flex items-center gap-2">
        <div className="flex-none">
          <AnimatedSelector
            name="panel-mode"
            value={panelMode}
            onChange={handlePanelModeChange}
            options={panelModeOptions}
            testIdPrefix="view-toggle"
          />
        </div>
        <div className="flex-1 min-w-0 flex justify-end overflow-hidden gap-2">
          {loadingVisible ? (
            <span
              className={`loading-pill loading-pill--compact ${
                showLoadingIndicator ? "" : "loading-pill--hide"
              }`}
              onTransitionEnd={(event) => {
                if (event.target !== event.currentTarget) {
                  return;
                }
                if (event.propertyName !== "opacity") {
                  return;
                }
                if (!showLoadingIndicator) {
                  setLoadingVisible(false);
                }
              }}
            >
              <span className="loading-spinner" aria-hidden="true" />
              Loading
            </span>
          ) : null}
          <SearchInput
            value={searchQuery}
            onChange={handleSearchChange}
            onClear={handleSearchClear}
            placeholder="Search issues..."
          />
          {showTypeFilterToolbar ? (
            <AnimatedSelector
              name="view"
              value={typeFilterValue}
              onChange={handleTypeFilterChange}
              options={typeFilterOptions}
            />
          ) : null}
        </div>
        <button
          className="flex-none toggle-button rounded-full bg-[var(--column)] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted h-7 flex items-center justify-center gap-2"
          onClick={() => {
            if (filterOpen) {
              closeSidebar("filter");
            } else {
              openSidebar("filter");
            }
          }}
          type="button"
          data-testid="filter-button"
        >
          <span className="toggle-row flex items-center gap-2">
            <Filter className="h-4 w-4" />
            <span className={`${toggleMotionClass} whitespace-nowrap label-text toggle-label`}>
              Filter
            </span>
          </span>
        </button>
        <button
          className="flex-none flex items-center gap-2 rounded-full bg-[var(--column)] px-2 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted h-8"
          onClick={() => {
            if (settingsOpen) {
              closeSidebar("settings");
            } else {
              openSidebar("settings");
            }
          }}
          type="button"
          data-testid="open-settings"
        >
          <SettingsIcon />
        </button>
      </div>

      {error && errorTime ? (
        <div className="mt-2">
          <ErrorStatusDisplay errorTime={errorTime} />
        </div>
      ) : error || columnError || routeError ? (
        <div className="mt-2 rounded-xl bg-card-muted p-3 text-sm text-muted">
          {error ?? routeError ?? columnError}
        </div>
      ) : null}

      <div className="mt-1 sm:mt-2 flex-1 min-h-0">
        <div
          ref={layoutFrameRef}
          className={`layout-frame h-full min-h-0${isResizing ? " is-resizing" : ""}${
            detailMaximized ? " detail-maximized" : ""
          }`}
        >
          <div
            className={`layout-main${sidebarReady ? " layout-main-animate" : ""}${
              sidebarPhase === "open" || sidebarPhase === "opening" ? " layout-main-pushed" : ""
            }`}
          >
            <div
              className={`view-track${sidebarReady ? " view-track-animate" : ""}${
                panelMode === "metrics" ? " view-track-metrics" : ""
              }`}
            >
              <div
                className="view-panel"
                data-testid="board-view"
                aria-hidden={panelMode !== "board"}
                hidden={panelMode !== "board"}
                style={{ display: panelMode === "board" ? undefined : "none" }}
              >
            <div
              className={`layout-slot layout-slot-board h-full p-0 min-[321px]:p-1 sm:p-2 md:p-3 overflow-hidden${
                detailMaximized ? " hidden" : ""
              }`}
            >
              {!detailMaximized ? (
                <Board
                  columns={columns}
                  issues={filteredIssues}
                  priorityLookup={priorityLookup}
                  config={config}
                  onSelectIssue={handleSelectIssue}
                  selectedIssueId={selectedTask?.id ?? null}
                  transitionKey={transitionKey}
                  detailOpen={isDetailOpen}
                  collapsedColumns={collapsedColumns}
                  motion={{ mode: "css" }}
                  onToggleCollapse={(column) => {
                    setCollapsedColumns((prev) => {
                      const next = new Set(prev);
                      if (next.has(column)) {
                        next.delete(column);
                      } else {
                        next.add(column);
                      }
                      return next;
                    });
                  }}
                />
              ) : null}
            </div>
                {isDetailVisible ? (
                  <div
                    className="detail-resizer h-full w-2 min-w-2 lg:w-3 lg:min-w-3 xl:w-4 xl:min-w-4 flex items-center justify-center cursor-col-resize pointer-events-auto"
                    role="separator"
                    onMouseDown={(event) => {
                      const frame = layoutFrameRef.current;
                      if (!frame) {
                        return;
                      }
                      event.preventDefault();
                      setIsResizing(true);
                      const rect = frame.getBoundingClientRect();
                      const effectiveWidth = detailMaximized ? 100 : detailWidth;
                      if (detailMaximized) {
                        setDetailWidth(100);
                        setDetailMaximized(false);
                      }
                      const startX = event.clientX;
                      const startWidth = effectiveWidth;
                      const handleMove = (moveEvent: MouseEvent) => {
                        const delta = moveEvent.clientX - startX;
                        const pixelWidth = (startWidth / 100) * rect.width - delta;
                        const clampedPixels = Math.max(320, Math.min(rect.width, pixelWidth));
                        const clamped = (clampedPixels / rect.width) * 100;
                        setDetailWidth(clamped);
                      };
                      const handleUp = () => {
                        window.removeEventListener("mousemove", handleMove);
                        window.removeEventListener("mouseup", handleUp);
                        setIsResizing(false);
                      };
                      window.addEventListener("mousemove", handleMove);
                      window.addEventListener("mouseup", handleUp);
                    }}
                    onTouchStart={(event) => {
                      const frame = layoutFrameRef.current;
                      if (!frame) {
                        return;
                      }
                      const touch = event.touches[0];
                      if (!touch) {
                        return;
                      }
                      setIsResizing(true);
                      const rect = frame.getBoundingClientRect();
                      const effectiveWidth = detailMaximized ? 100 : detailWidth;
                      if (detailMaximized) {
                        setDetailWidth(100);
                        setDetailMaximized(false);
                      }
                      const startX = touch.clientX;
                      const startWidth = effectiveWidth;
                      const handleMove = (moveEvent: TouchEvent) => {
                        const moveTouch = moveEvent.touches[0];
                        if (!moveTouch) {
                          return;
                        }
                        const delta = moveTouch.clientX - startX;
                        const pixelWidth = (startWidth / 100) * rect.width - delta;
                        const clampedPixels = Math.max(320, Math.min(rect.width, pixelWidth));
                        const clamped = (clampedPixels / rect.width) * 100;
                        setDetailWidth(clamped);
                      };
                      const handleUp = () => {
                        window.removeEventListener("touchmove", handleMove);
                        window.removeEventListener("touchend", handleUp);
                        setIsResizing(false);
                      };
                      window.addEventListener("touchmove", handleMove);
                      window.addEventListener("touchend", handleUp);
                    }}
                  >
                    <span className="h-5 w-1 rounded-full bg-[var(--gray-5)]" />
                  </div>
                ) : null}
                <TaskDetailPanel
                  task={selectedTask}
                  allIssues={issues}
                  isOpen={isDetailOpen}
                  isVisible={isDetailVisible}
                  navDirection={detailNavDirection}
                  widthPercent={detailMaximized ? 100 : detailWidth}
                  columns={columns}
                  priorityLookup={priorityLookup}
                  config={config}
                  apiBase={apiBase}
                  onClose={handleTaskClose}
                  onToggleMaximize={() => setDetailMaximized((prev) => !prev)}
                  isMaximized={detailMaximized}
                  onAfterClose={() => setDetailClosing(false)}
                  onFocus={handleFocus}
                  focusedIssueId={focusedIssueId}
                  focusedCommentId={focusedCommentId}
                  onNavigateToDescendant={handleSelectIssue}
                />
              </div>
              <div
                className="view-panel"
                style={{ display: panelMode === "metrics" ? undefined : "none" }}
              >
                <div
                  className="layout-slot layout-slot-metrics h-full p-0 min-[321px]:p-1 sm:p-2 md:p-3"
                  data-testid="metrics-view"
                  aria-hidden={panelMode !== "metrics"}
                  hidden={panelMode !== "metrics"}
                >
                  {config ? (
                    <MetricsPanel
                      issues={metricsIssues}
                      config={config}
                      hasLocalIssues={hasLocalIssues}
                      projectLabels={projectLabels}
                    />
                  ) : null}
                </div>
              </div>
            </div>
          </div>
        <FilterSidebar
          isOpen={sidebarPhase === "open" && activeSidebar === "filter"}
          isVisible={
            sidebarPhase !== "closed"
            && (activeSidebar === "filter" || exitingSidebar === "filter")
          }
          animate={sidebarReady}
          onTransitionEnd={handleSidebarTransitionEnd}
          onClose={() => closeSidebar("filter")}
          focusedIssueLabel={focusedIssueLabel}
          onClearFocus={clearFocus}
          projectLabels={projectLabels}
          enabledProjects={effectiveEnabledProjects}
          onToggleProject={handleToggleProject}
          hasVirtualProjects={hasVirtualProjects}
          hasLocalIssues={hasLocalIssues}
          showLocal={showLocal}
          showShared={showShared}
          onToggleLocal={() => setShowLocal((prev) => !prev)}
          onToggleShared={() => setShowShared((prev) => !prev)}
            typeOptions={typeFilterOptions}
            typeValue={typeFilterValue}
            onTypeChange={handleTypeFilterChange}
          />
          <SettingsPanel
            isOpen={sidebarPhase === "open" && activeSidebar === "settings"}
            isVisible={
              sidebarPhase !== "closed"
              && (activeSidebar === "settings" || exitingSidebar === "settings")
            }
            animate={sidebarReady}
            onTransitionEnd={handleSidebarTransitionEnd}
            onClose={() => closeSidebar("settings")}
            showTypeFilterToolbar={showTypeFilterToolbar}
            showInitiativesInTypeFilter={showInitiativesInTypeFilter}
            onToggleShowTypeFilterToolbar={() => setShowTypeFilterToolbar((prev) => !prev)}
            onToggleShowInitiativesInTypeFilter={() => setShowInitiativesInTypeFilter((prev) => !prev)}
          />
        </div>
      </div>
    </AppShell>
  );
}
