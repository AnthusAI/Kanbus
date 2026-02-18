import React, { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  CheckCheck,
  Filter,
  FilterX,
  Lightbulb,
  ListChecks,
  Search,
  SquareCheckBig,
  X
} from "lucide-react";
import { AppShell } from "./components/AppShell";
import { Board } from "./components/Board";
import { TaskDetailPanel } from "./components/TaskDetailPanel";
import { ErrorStatusDisplay } from "./components/ErrorStatusDisplay";
import { AnimatedSelector } from "@kanbus/ui";
import { SettingsPanel } from "./components/SettingsPanel";
import { SearchInput } from "./components/SearchInput";
import {
  fetchSnapshot,
  subscribeToSnapshots,
  subscribeToNotifications,
  type NotificationEvent,
} from "./api/client";
import { installConsoleTelemetry } from "./utils/console-telemetry";
import { matchesSearchQuery } from "./utils/issue-search";
import type { Issue, IssuesSnapshot, ProjectConfig } from "./types/issues";
import { useAppearance } from "./hooks/useAppearance";

type ViewMode = "initiatives" | "epics" | "issues";
type NavAction = "push" | "pop" | "none";
type RouteContext = {
  account: string | null;
  project: string | null;
  basePath: string | null;
  viewMode: ViewMode | null;
  issueId: string | null;
  parentId: string | null;
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

function parseRoute(pathname: string): RouteContext {
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

function navigate(
  path: string,
  setRoute: (route: RouteContext) => void,
  navActionRef?: React.MutableRefObject<NavAction>
) {
  window.history.pushState({}, "", path);
  if (navActionRef) {
    navActionRef.current = "push";
  }
  setRoute(parseRoute(path));
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
  return config.statuses.map((s) => s.name);
}

function getInitialCollapsedColumns(config: ProjectConfig): Set<string> {
  return new Set(
    config.statuses.filter((s) => s.collapsed).map((s) => s.name)
  );
}

const VIEW_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  initiatives: Lightbulb,
  epics: ListChecks,
  issues: SquareCheckBig,
  "sub-tasks": CheckCheck
};

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
  const [loadingVisible, setLoadingVisible] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Issue | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [collapsedColumns, setCollapsedColumns] = useState<Set<string>>(new Set());
  const [isResizing, setIsResizing] = useState(false);
  const [detailWidth, setDetailWidth] = useState(() => loadStoredDetailWidth());
  const [detailMaximized, setDetailMaximized] = useState(false);
  const [focusedIssueId, setFocusedIssueId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [route, setRoute] = useState<RouteContext>(() =>
    parseRoute(window.location.pathname)
  );
  const [detailClosing, setDetailClosing] = useState(false);
  const [detailNavDirection, setDetailNavDirection] = useState<NavAction>("none");
  const layoutFrameRef = React.useRef<HTMLDivElement | null>(null);
  const navActionRef = React.useRef<NavAction>("none");
  const wasDetailOpenRef = React.useRef(false);
  const collapsedColumnsInitialized = React.useRef(false);
  useAppearance();
  const config = snapshot?.config;
  const issues = snapshot?.issues ?? [];
  const deferredIssues = useDeferredValue(issues);

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
      setRoute(parseRoute(window.location.pathname));
    };
    window.addEventListener("popstate", handlePop);
    return () => window.removeEventListener("popstate", handlePop);
  }, []);

  useEffect(() => {
    const parsed = parseRoute(window.location.pathname);
    if (
      parsed.basePath !== route.basePath
      || parsed.issueId !== route.issueId
      || parsed.parentId !== route.parentId
      || parsed.viewMode !== route.viewMode
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
            break;
          case "issue_created":
          case "issue_updated":
          case "issue_deleted":
            // Trigger immediate snapshot refresh for CRUD operations
            fetchSnapshot(apiBase).then(setSnapshot).catch(console.error);
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

  // Auto-select focused issue in detail panel
  useEffect(() => {
    if (!focusedIssueId || !snapshot) {
      return;
    }
    const projectKey = snapshot.config.project_key;
    const resolved = resolveIssueByIdentifier(snapshot.issues, focusedIssueId, projectKey);
    if (resolved.issue) {
      // Navigate to the issue detail URL, which will trigger routeContext update
      // and properly set selectedTask via the normal route handling
      // basePath can be empty string "" for root-level deployments
      const issueUrl = `${route.basePath}/issues/${resolved.issue.id}`;
      navigate(issueUrl, setRoute, navActionRef);
    }
  }, [focusedIssueId, snapshot, route.basePath]);

  useEffect(() => {
    if (!viewMode) {
      return;
    }
    window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode);
  }, [viewMode]);

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
  };

  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
  };

  const handleSearchClear = () => {
    setSearchQuery("");
  };

  const handleUiControlAction = (action: NotificationEvent extends { type: "ui_control"; action: infer A } ? A : never) => {
    switch (action.action) {
      case "clear_focus":
        setFocusedIssueId(null);
        break;
      case "set_view_mode":
        if (route.basePath != null) {
          const nextMode = action.mode as ViewMode;
          navigate(`${route.basePath}/${nextMode}/`, setRoute, navActionRef);
        }
        break;
      case "set_search":
        setSearchQuery(action.query);
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
        setSettingsOpen((prev) => !prev);
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
            const issueUrl = `${route.basePath}/issues/${resolved.issue.id}`;
            navigate(issueUrl, setRoute, navActionRef);
          }
        }
        break;
    }
  };

  const filteredIssues = useMemo(() => {
    // Use non-deferred issues when search is active for immediate feedback
    const sourceIssues = searchQuery.trim() ? issues : deferredIssues;
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

    return result;
  }, [issues, deferredIssues, resolvedViewMode, routeContext.parentIssue, route.parentId, focusedIssueId, searchQuery]);

  const handleSelectIssue = (issue: Issue) => {
    if (route.basePath == null) {
      return;
    }
    if (route.parentId) {
      navigate(
        `${route.basePath}/issues/${route.parentId}/${issue.id}`,
        setRoute,
        navActionRef
      );
      return;
    }
    navigate(`${route.basePath}/issues/${issue.id}`, setRoute, navActionRef);
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
          <AnimatedSelector
            name="view"
            value={resolvedViewMode}
            onChange={(value) => {
              if (route.basePath == null) {
                return;
              }
              const next = value as ViewMode;
              navigate(`${route.basePath}/${next}/`, setRoute, navActionRef);
            }}
            options={[
              {
                id: "initiatives",
                label: "Initiatives",
                content: (
                  <span className="selector-option">
                  {React.createElement(VIEW_ICONS.initiatives, { className: "h-4 w-4" })}
                    <span className="selector-label">Initiatives</span>
                  </span>
                )
              },
              {
                id: "epics",
                label: "Epics",
                content: (
                  <span className="selector-option">
                  {React.createElement(VIEW_ICONS.epics, { className: "h-4 w-4" })}
                    <span className="selector-label">Epics</span>
                  </span>
                )
              },
              {
                id: "issues",
                label: "Issues",
                content: (
                  <span className="selector-option">
                  {React.createElement(VIEW_ICONS.issues, { className: "h-4 w-4" })}
                    <span className="selector-label">Issues</span>
                  </span>
                )
              }
            ]}
          />
        </div>
        <button
          className="flex-none toggle-button rounded-full bg-[var(--column)] px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted h-7 flex items-center justify-center gap-2"
          onClick={() => {
            // Placeholder for future filter functionality
            if (focusedIssueId) {
              setFocusedIssueId(null);
            }
          }}
          type="button"
          data-testid="filter-button"
        >
          <span className="toggle-row flex items-center gap-2">
            <Filter className="h-4 w-4" />
            <span className={`${toggleMotionClass} whitespace-nowrap label-text toggle-label`}>
              {focusedIssueId ? "Focused" : "Filter"}
            </span>
          </span>
        </button>
        <button
          className="flex-none flex items-center gap-2 rounded-full bg-[var(--column)] px-2 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted h-8"
          onClick={() => setSettingsOpen(true)}
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

      <div className="mt-2 flex-1 min-h-0">
        <div
          ref={layoutFrameRef}
          className={`layout-frame h-full min-h-0${isResizing ? " is-resizing" : ""}`}
        >
          <div className="layout-slot layout-slot-board h-full pt-2 px-0">
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
              onClose={() => {
                setDetailClosing(true);
                setDetailMaximized(false);
                if (route.basePath == null) {
                  setSelectedTask(null);
                  return;
                }
                setSelectedTask(null);
                const nextMode = resolvedViewMode ?? loadStoredViewMode();
                navigate(`${route.basePath}/${nextMode}/`, setRoute, navActionRef);
              }}
              onToggleMaximize={() => setDetailMaximized((prev) => !prev)}
              isMaximized={detailMaximized}
              onAfterClose={() => setDetailClosing(false)}
              onFocus={handleFocus}
              focusedIssueId={focusedIssueId}
              onNavigateToDescendant={handleSelectIssue}
            />
          </div>
      </div>

      <SettingsPanel isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </AppShell>
  );
}
