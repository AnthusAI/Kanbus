import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import type { PanelMode, ViewMode } from "../types/console";
import {
  DETAIL_WIDTH_STORAGE_KEY,
  ENABLED_PROJECTS_STORAGE_KEY,
  PANEL_MODE_STORAGE_KEY,
  SHOW_INITIATIVES_IN_TYPE_FILTER_KEY,
  SHOW_LOCAL_STORAGE_KEY,
  SHOW_SHARED_STORAGE_KEY,
  SHOW_TYPE_FILTER_TOOLBAR_KEY,
  VIEW_MODE_STORAGE_KEY,
  loadStoredBoolean,
  loadStoredDetailWidth,
  loadStoredEnabledProjects,
  loadStoredPanelMode,
  loadStoredViewMode,
} from "../utils/ui-preferences-storage";

export type PersistedUiPrefs = {
  viewMode: ViewMode | null;
  setViewMode: Dispatch<SetStateAction<ViewMode | null>>;
  panelMode: PanelMode;
  setPanelMode: Dispatch<SetStateAction<PanelMode>>;
  detailWidth: number;
  setDetailWidth: Dispatch<SetStateAction<number>>;
  enabledProjects: Set<string> | null;
  setEnabledProjects: Dispatch<SetStateAction<Set<string> | null>>;
  showLocal: boolean;
  setShowLocal: Dispatch<SetStateAction<boolean>>;
  showShared: boolean;
  setShowShared: Dispatch<SetStateAction<boolean>>;
  showTypeFilterToolbar: boolean;
  setShowTypeFilterToolbar: Dispatch<SetStateAction<boolean>>;
  showInitiativesInTypeFilter: boolean;
  setShowInitiativesInTypeFilter: Dispatch<SetStateAction<boolean>>;
};

export function usePersistedUiPrefs(): PersistedUiPrefs {
  const [viewMode, setViewMode] = useState<ViewMode | null>(() => loadStoredViewMode());
  const [panelMode, setPanelMode] = useState<PanelMode>(() => loadStoredPanelMode());
  const [detailWidth, setDetailWidth] = useState(() => loadStoredDetailWidth());
  const [enabledProjects, setEnabledProjects] = useState<Set<string> | null>(() =>
    loadStoredEnabledProjects()
  );
  const [showLocal, setShowLocal] = useState(() => loadStoredBoolean(SHOW_LOCAL_STORAGE_KEY, true));
  const [showShared, setShowShared] = useState(() => loadStoredBoolean(SHOW_SHARED_STORAGE_KEY, true));
  const [showTypeFilterToolbar, setShowTypeFilterToolbar] = useState(() =>
    loadStoredBoolean(SHOW_TYPE_FILTER_TOOLBAR_KEY, true)
  );
  const [showInitiativesInTypeFilter, setShowInitiativesInTypeFilter] = useState(() =>
    loadStoredBoolean(SHOW_INITIATIVES_IN_TYPE_FILTER_KEY, true)
  );

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
    window.localStorage.setItem(SHOW_TYPE_FILTER_TOOLBAR_KEY, String(showTypeFilterToolbar));
  }, [showTypeFilterToolbar]);

  useEffect(() => {
    window.localStorage.setItem(
      SHOW_INITIATIVES_IN_TYPE_FILTER_KEY,
      String(showInitiativesInTypeFilter)
    );
  }, [showInitiativesInTypeFilter]);

  return {
    viewMode,
    setViewMode,
    panelMode,
    setPanelMode,
    detailWidth,
    setDetailWidth,
    enabledProjects,
    setEnabledProjects,
    showLocal,
    setShowLocal,
    showShared,
    setShowShared,
    showTypeFilterToolbar,
    setShowTypeFilterToolbar,
    showInitiativesInTypeFilter,
    setShowInitiativesInTypeFilter,
  };
}
