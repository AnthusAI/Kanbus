import type { PanelMode, ViewMode } from "../types/console";

export const VIEW_MODE_STORAGE_KEY = "kanbus.console.viewMode";
export const DETAIL_WIDTH_STORAGE_KEY = "kanbus.console.detailWidth";
export const ENABLED_PROJECTS_STORAGE_KEY = "kanbus.console.enabledProjects";
export const SHOW_LOCAL_STORAGE_KEY = "kanbus.console.showLocal";
export const SHOW_SHARED_STORAGE_KEY = "kanbus.console.showShared";
export const SHOW_TYPE_FILTER_TOOLBAR_KEY = "kanbus.console.showTypeFilterToolbar";
export const SHOW_INITIATIVES_IN_TYPE_FILTER_KEY = "kanbus.console.showInitiativesInTypeFilter";
export const PANEL_MODE_STORAGE_KEY = "kanbus.console.panelMode";

export function loadStoredEnabledProjects(): Set<string> | null {
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
    return null;
  }
  return null;
}

export function loadStoredBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === "undefined") {
    return fallback;
  }
  const stored = window.localStorage.getItem(key);
  if (stored === "false") {
    return false;
  }
  return fallback;
}

export function loadStoredViewMode(): ViewMode {
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

export function loadStoredPanelMode(): PanelMode {
  if (typeof window === "undefined") {
    return "board";
  }
  const stored = window.localStorage.getItem(PANEL_MODE_STORAGE_KEY);
  if (
    stored === "metrics"
    || stored === "board"
    || stored === "wiki"
    || stored === "now"
  ) {
    return stored as PanelMode;
  }
  return "board";
}

export function loadStoredDetailWidth(): number {
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
