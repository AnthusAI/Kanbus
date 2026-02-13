import React, { useEffect, useMemo, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { AppShell } from "./components/AppShell";
import { Board } from "./components/Board";
import { TaskDetailPanel } from "./components/TaskDetailPanel";
import { AnimatedSelector } from "./components/ui/animated-selector";
import { SettingsPanel } from "./components/SettingsPanel";
import { fetchSnapshot, subscribeToSnapshots } from "./api/client";
import type { Issue, IssuesSnapshot, ProjectConfig } from "./types/issues";
import { useAppearance } from "./hooks/useAppearance";

type ViewMode = "initiatives" | "epics" | "tasks";

const VIEW_MODE_STORAGE_KEY = "taskulus.console.viewMode";
const SHOW_CLOSED_STORAGE_KEY = "taskulus.console.showClosed";

function loadStoredViewMode(): ViewMode {
  if (typeof window === "undefined") {
    return "epics";
  }
  const stored = window.localStorage.getItem(VIEW_MODE_STORAGE_KEY);
  if (stored === "initiatives" || stored === "epics" || stored === "tasks") {
    return stored;
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

function buildPriorityLookup(config: ProjectConfig): Record<number, string> {
  return Object.entries(config.priorities).reduce<Record<number, string>>(
    (accumulator, [key, value]) => {
      accumulator[Number(key)] = value;
      return accumulator;
    },
    {}
  );
}

function getStatusColumns(config: ProjectConfig): string[] {
  const workflow = config.workflows.default;
  return Object.keys(workflow || {});
}

function SettingsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-3 w-3">
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
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>(() => loadStoredViewMode());
  const [selectedTask, setSelectedTask] = useState<Issue | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showClosed, setShowClosed] = useState(() => loadStoredShowClosed());
  useAppearance();
  const config = snapshot?.config;
  const issues = snapshot?.issues ?? [];

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    fetchSnapshot()
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
  }, []);

  useEffect(() => {
    setSelectedTask(null);
  }, [viewMode]);

  useEffect(() => {
    window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode);
  }, [viewMode]);

  useEffect(() => {
    window.localStorage.setItem(SHOW_CLOSED_STORAGE_KEY, String(showClosed));
  }, [showClosed]);

  useEffect(() => {
    if (!selectedTask) {
      return;
    }
    const stillExists = issues.some((issue) => issue.id === selectedTask.id);
    if (!stillExists) {
      setSelectedTask(null);
    }
  }, [issues, selectedTask]);

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
  const columnError =
    config && columns.length === 0
      ? "default workflow is required to render columns"
      : null;

  const taskLevelTypes = useMemo(() => {
    const configuredTypes = config?.types ?? [];
    return ["task", ...configuredTypes];
  }, [config?.types]);

  const filteredIssues = useMemo(() => {
    if (viewMode === "initiatives") {
      return issues.filter((issue) => issue.type === "initiative");
    }
    if (viewMode === "epics") {
      return issues.filter((issue) => issue.type === "epic");
    }
    return issues.filter((issue) => taskLevelTypes.includes(issue.type));
  }, [issues, taskLevelTypes, viewMode]);

  const subTasks = useMemo(() => {
    if (!selectedTask) {
      return [];
    }
    return issues.filter(
      (issue) => issue.type === "sub-task" && issue.parent === selectedTask.id
    );
  }, [issues, selectedTask]);

  const handleSelectIssue = (issue: Issue) => {
    if (taskLevelTypes.includes(issue.type)) {
      setSelectedTask(issue);
    }
  };

  const transitionKey = `${viewMode}-${showClosed}-${filteredIssues.length}-${snapshot?.updated_at ?? ""}`;

  return (
    <AppShell>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <AnimatedSelector
          name="view"
          value={viewMode}
          onChange={(value) => setViewMode(value as ViewMode)}
          options={[
            { id: "initiatives", label: "Initiatives" },
            { id: "epics", label: "Epics" },
            { id: "tasks", label: "Tasks" }
          ]}
        />
        <div className="flex items-center gap-3">
          <button
            className="rounded-full bg-card-muted px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted"
            onClick={() => setShowClosed((prev) => !prev)}
            type="button"
            data-testid="toggle-closed"
          >
            <span className="flex items-center gap-2">
              {showClosed ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
              {showClosed ? "Hide closed" : "Show closed"}
            </span>
          </button>
          <button
            className="flex items-center gap-2 rounded-full bg-card-muted px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted"
            onClick={() => setSettingsOpen(true)}
            type="button"
            data-testid="open-settings"
          >
            <SettingsIcon />
            <span>Settings</span>
          </button>
        </div>
      </div>

      {error || columnError ? (
        <div className="mt-3 rounded-xl bg-card-muted p-3 text-sm text-muted">
          {error ?? columnError}
        </div>
      ) : null}

      <div className="mt-3">
        {!snapshot ? (
          <div className="rounded-2xl bg-card-muted p-3 text-sm text-muted">
            Waiting for project data.
          </div>
        ) : (
          <Board
            columns={columns}
            issues={filteredIssues}
            priorityLookup={priorityLookup}
            onSelectIssue={handleSelectIssue}
            transitionKey={transitionKey}
          />
        )}
      </div>

      {selectedTask ? (
        <TaskDetailPanel
          task={selectedTask}
          subTasks={subTasks}
          columns={columns}
          priorityLookup={priorityLookup}
          onClose={() => setSelectedTask(null)}
        />
      ) : null}

      <SettingsPanel isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </AppShell>
  );
}
