import React, { useEffect, useMemo, useState } from "react";
import {
  CheckCheck,
  Filter,
  FilterX,
  Lightbulb,
  ListChecks,
  SquareCheckBig
} from "lucide-react";
import { AppShell } from "./components/AppShell";
import { Board } from "./components/Board";
import { TaskDetailPanel } from "./components/TaskDetailPanel";
import { AnimatedSelector } from "./components/ui/animated-selector";
import { SettingsPanel } from "./components/SettingsPanel";
import { fetchSnapshot, subscribeToSnapshots } from "./api/client";
import type { Issue, IssuesSnapshot, ProjectConfig } from "./types/issues";
import { useAppearance } from "./hooks/useAppearance";

type ViewMode = "initiatives" | "epics" | "issues";
type RouteContext = {
  account: string | null;
  project: string | null;
  basePath: string | null;
  viewMode: ViewMode | null;
  issueId: string | null;
  parentId: string | null;
  error: string | null;
};

const VIEW_MODE_STORAGE_KEY = "kanbus.console.viewMode";
const SHOW_CLOSED_STORAGE_KEY = "kanbus.console.showClosed";
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

function loadStoredShowClosed(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const stored = window.localStorage.getItem(SHOW_CLOSED_STORAGE_KEY);
  if (stored === "true") {
    return true;
  }
  if (stored === "false") {
    return false;
  }
  return false;
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

function navigate(path: string, setRoute: (route: RouteContext) => void) {
  window.history.pushState({}, "", path);
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
  const workflow = config.workflows.default;
  return Object.keys(workflow || {});
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
  const [routeError, setRouteError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode | null>(() =>
    loadStoredViewMode()
  );
  const [selectedTask, setSelectedTask] = useState<Issue | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showClosed, setShowClosed] = useState(() => loadStoredShowClosed());
  const [isResizing, setIsResizing] = useState(false);
  const [detailWidth, setDetailWidth] = useState(() => loadStoredDetailWidth());
  const [route, setRoute] = useState<RouteContext>(() =>
    parseRoute(window.location.pathname)
  );
  const layoutRef = React.useRef<HTMLDivElement | null>(null);
  useAppearance();
  const config = snapshot?.config;
  const issues = snapshot?.issues ?? [];

  useEffect(() => {
    const handlePop = () => {
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
    if (!route.basePath) {
      setError("URL must include /:account/:project");
      setLoading(false);
      return () => {};
    }
    const apiBase = `${route.basePath}/api`;
    fetchSnapshot(apiBase)
      .then((data) => {
        if (isMounted) {
          setSnapshot(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Failed to load data");
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
      },
      () => {
        setError("SSE connection issue. Attempting to reconnect.");
      }
    );

    return () => {
      isMounted = false;
      unsubscribe();
    };
  }, [route.basePath]);

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
    window.localStorage.setItem(SHOW_CLOSED_STORAGE_KEY, String(showClosed));
  }, [showClosed]);

  useEffect(() => {
    window.localStorage.setItem(DETAIL_WIDTH_STORAGE_KEY, String(detailWidth));
  }, [detailWidth]);

  useEffect(() => {
    const layout = layoutRef.current;
    if (!layout) {
      return;
    }
    layout.style.setProperty("--detail-width", `${detailWidth}%`);
    layout.style.setProperty("--board-width", `${100 - detailWidth}%`);
  }, [detailWidth]);

  useEffect(() => {
    if (!selectedTask) {
      return;
    }
    const updatedTask = issues.find((issue) => issue.id === selectedTask.id);
    if (!updatedTask) {
      if (route.basePath) {
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
  }, [issues, route.basePath, selectedTask, viewMode]);

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
    const allColumns = getStatusColumns(config);
    if (showClosed) {
      return allColumns;
    }
    return allColumns.filter((column) => column !== "closed");
  }, [config, showClosed]);
  const activeViewMode = route.parentId
    ? null
    : route.viewMode ?? viewMode ?? null;
  const columnError =
    config && columns.length === 0
      ? "default workflow is required to render columns"
      : null;

  const issueLevelTypes = useMemo(() => {
    const configuredTypes = config?.types ?? [];
    return ["task", ...configuredTypes];
  }, [config?.types]);

  const routeContext = useMemo(() => {
    if (!route.basePath) {
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
      const derivedViewMode =
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

  useEffect(() => {
    setRouteError(routeContext.error);
    setViewMode(routeContext.viewMode);
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

  const filteredIssues = useMemo(() => {
    if (routeContext.parentIssue) {
      const ids = collectDescendants(issues, routeContext.parentIssue.id);
      return issues.filter((issue) => ids.has(issue.id));
    }
    if (route.parentId) {
      return [];
    }
    if (activeViewMode === "initiatives") {
      return issues.filter((issue) => issue.type === "initiative");
    }
    if (activeViewMode === "epics") {
      return issues.filter((issue) => issue.type === "epic");
    }
    if (activeViewMode === "issues") {
      return issues.filter((issue) => issueLevelTypes.includes(issue.type));
    }
    return issues;
  }, [activeViewMode, issues, issueLevelTypes, routeContext.parentIssue, route.parentId]);

  const subTasks = useMemo(() => {
    if (!selectedTask) {
      return [];
    }
    return issues.filter(
      (issue) => issue.type === "sub-task" && issue.parent === selectedTask.id
    );
  }, [issues, selectedTask]);

  const handleSelectIssue = (issue: Issue) => {
    if (!route.basePath) {
      return;
    }
    if (route.parentId) {
      navigate(`${route.basePath}/issues/${route.parentId}/${issue.id}`, setRoute);
      return;
    }
    navigate(`${route.basePath}/issues/${issue.id}`, setRoute);
  };

  const motionMode = typeof document !== "undefined" ? document.documentElement.dataset.motion : "full";
  const toggleMotionClass =
    motionMode === "off"
      ? ""
      : motionMode === "reduced"
      ? "transition-opacity duration-150"
      : "transition-opacity duration-300";

  const transitionKey = `${activeViewMode ?? "none"}-${showClosed}-${snapshot?.updated_at ?? ""}`;

  return (
    <AppShell>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <div className="flex items-center gap-2 ml-auto">
          <AnimatedSelector
            name="view"
            value={activeViewMode}
            onChange={(value) => {
              if (!route.basePath) {
                return;
              }
              const next = value as ViewMode;
              navigate(`${route.basePath}/${next}/`, setRoute);
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
          <button
            className="rounded-full bg-[var(--column)] px-2 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted h-8 flex items-center justify-center gap-2 max-md:px-2 max-md:gap-1 max-md:[&_span.label-text]:hidden"
            onClick={() => setShowClosed((prev) => !prev)}
            type="button"
            data-testid="toggle-closed"
          >
            <span className="flex items-center gap-2 max-md:gap-1">
              {showClosed ? <FilterX className="h-4 w-4" /> : <Filter className="h-4 w-4" />}
              <span className={`${toggleMotionClass} whitespace-nowrap label-text`}>
                {showClosed ? "All" : "Open"}
              </span>
            </span>
          </button>
          <button
            className="flex items-center gap-2 rounded-full bg-[var(--column)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted h-8"
            onClick={() => setSettingsOpen(true)}
            type="button"
            data-testid="open-settings"
          >
            <SettingsIcon />
          </button>
        </div>
      </div>

      {error || columnError || routeError ? (
        <div className="mt-2 rounded-xl bg-card-muted p-3 text-sm text-muted">
          {error ?? routeError ?? columnError}
        </div>
      ) : null}

      <div ref={layoutRef} className="mt-2 flex-1 min-h-0">
        {!snapshot ? (
          <div className="rounded-2xl bg-card-muted p-3 text-sm text-muted">
            Waiting for project data.
          </div>
        ) : (
          <div
            ref={layoutRef}
            className={`layout-frame h-full min-h-0${isResizing ? " is-resizing" : ""}`}
          >
            <div className="layout-slot layout-slot-board h-full pt-2 px-2 pr-0">
              <Board
                columns={columns}
                issues={filteredIssues}
                priorityLookup={priorityLookup}
                config={config}
                onSelectIssue={handleSelectIssue}
                selectedIssueId={selectedTask?.id ?? null}
                transitionKey={transitionKey}
              />
            </div>
            {selectedTask ? (
              <div
                className="detail-resizer h-full w-2 min-w-2 flex items-center justify-center cursor-col-resize pointer-events-auto"
                role="separator"
                onMouseDown={(event) => {
                  const container = layoutRef.current;
                  if (!container) {
                    return;
                  }
                  event.preventDefault();
                  setIsResizing(true);
                  const rect = container.getBoundingClientRect();
                  const startX = event.clientX;
                  const startWidth = detailWidth;
                  const handleMove = (moveEvent: MouseEvent) => {
                    const delta = moveEvent.clientX - startX;
                    const next = ((startWidth / 100) * rect.width - delta) / rect.width * 100;
                    const clamped = Math.min(60, Math.max(20, next));
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
                  const container = layoutRef.current;
                  if (!container) {
                    return;
                  }
                  const touch = event.touches[0];
                  if (!touch) {
                    return;
                  }
                  setIsResizing(true);
                  const rect = container.getBoundingClientRect();
                  const startX = touch.clientX;
                  const startWidth = detailWidth;
                  const handleMove = (moveEvent: TouchEvent) => {
                    const moveTouch = moveEvent.touches[0];
                    if (!moveTouch) {
                      return;
                    }
                    const delta = moveTouch.clientX - startX;
                    const next = ((startWidth / 100) * rect.width - delta) / rect.width * 100;
                    const clamped = Math.min(60, Math.max(20, next));
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
              subTasks={subTasks}
              isOpen={Boolean(selectedTask)}
              widthPercent={detailWidth}
              columns={columns}
              priorityLookup={priorityLookup}
              config={config}
              onClose={() => {
                if (!route.basePath) {
                  setSelectedTask(null);
                  return;
                }
                const nextMode = activeViewMode ?? loadStoredViewMode();
                navigate(`${route.basePath}/${nextMode}/`, setRoute);
              }}
            />
          </div>
        )}
      </div>

      <SettingsPanel isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </AppShell>
  );
}
