import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "./components/AppShell";
import { useBoardColumnState, getConfiguredIssueTypes, issueTypeFromFilter, getStatusColumnsForTypeFilter, getStatusColumnsForIssueTypes } from "@kanbus/ui";
import { ConsoleToolbar } from "./components/ConsoleToolbar";
import { ConsoleViewTrack } from "./components/ConsoleViewTrack";
import { ErrorStatusDisplay } from "./components/ErrorStatusDisplay";
import { FilterSidebar } from "./components/FilterSidebar";
import { SettingsPanel } from "./components/SettingsPanel";
import { buildPanelModeOptions, buildTypeFilterOptions } from "./components/selectorOptions";
import { reuseUnchangedIssues } from "./utils/reuse-unchanged-issues";
import { useStructurallyStableValue } from "./hooks/useStructurallyStableValue";
import type { UiControlAction } from "./api/client";
import type { Issue } from "./types/issues";
import type { IssueSelectionContext, NavAction, PanelMode, ViewMode } from "./types/console";
import { buildUrl, navigate, parseRoute, replaceCurrentRoute } from "./utils/console-route";
import {
  buildPriorityLookup,
  collectDescendants,
  computeViewModeCounts,
  resolveBoardTypeFilter,
  resolveIssueByIdentifier,
  resolveRouteContext,
} from "./utils/issue-selection";
import { loadStoredViewMode } from "./utils/ui-preferences-storage";
import { useAppearance } from "./hooks/useAppearance";
import { useCloudAuth } from "./hooks/useCloudAuth";
import { useConsoleRoute } from "./hooks/useConsoleRoute";
import { useDetailPanelLayout } from "./hooks/useDetailPanelLayout";
import { useFilteredIssues } from "./hooks/useFilteredIssues";
import { useFocusAndSearch } from "./hooks/useFocusAndSearch";
import { usePersistedUiPrefs } from "./hooks/usePersistedUiPrefs";
import { useProjectFilters } from "./hooks/useProjectFilters";
import { useRealtimeNotifications } from "./hooks/useRealtimeNotifications";
import { useSidebarPanels } from "./hooks/useSidebarPanels";
import { useSnapshotFeed } from "./hooks/useSnapshotFeed";
import { useViewModeSync } from "./hooks/useViewModeSync";

export default function App() {
  useAppearance();
  const { route, setRoute, navActionRef } = useConsoleRoute();
  const {
    viewMode, setViewMode, panelMode, setPanelMode, detailWidth, setDetailWidth,
    enabledProjects, setEnabledProjects, showLocal, setShowLocal, showShared, setShowShared,
    showTypeFilterToolbar, setShowTypeFilterToolbar,
    showInitiativesInTypeFilter, setShowInitiativesInTypeFilter,
  } = usePersistedUiPrefs();
  const visitedPanelModesRef = useRef(new Set<PanelMode>());
  visitedPanelModesRef.current.add(panelMode);
  const feed = useSnapshotFeed(route.basePath, panelMode);
  const { snapshot, error, errorTime, loading, apiBase, refreshSnapshot } = feed;
  const [routeError, setRouteError] = useState<string | null>(null);
  const [wikiDirty, setWikiDirty] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Issue | null>(null);
  const [detailNavDirection, setDetailNavDirection] = useState<NavAction>("none");
  const lastTypeSelectionRef = useRef<string | null>(null);

  useEffect(() => {
    if (route.wikiPath !== null) {
      setPanelMode("wiki");
    }
  }, [route.wikiPath]);

  useCloudAuth(route.basePath, feed);
  const {
    focusedIssueId, setFocusedIssueId, focusedCommentId, setFocusedCommentId,
    searchQuery, setSearchQuery, handleFocus, handleSearchChange, handleSearchClear, clearFocus,
  } = useFocusAndSearch(route, setRoute, navActionRef, snapshot);

  const config = useStructurallyStableValue(snapshot?.config);
  const { collapsedColumns, setCollapsedColumns, toggleColumn } = useBoardColumnState({
    config, storageKey: config ? `kanbus.console.columns.v1.${config.project_key}` : undefined,
  });
  const previousIssuesByIdRef = useRef<ReadonlyMap<string, Issue>>(new Map());
  const issues = useMemo(() => {
    const list = snapshot?.issues ?? [];
    if (!list.length) return [];
    const issuesById = reuseUnchangedIssues(previousIssuesByIdRef.current, list);
    previousIssuesByIdRef.current = issuesById;
    return Array.from(issuesById.values());
  }, [snapshot?.issues]);
  const deferredIssues = useDeferredValue(issues);
  const showAllTypes = route.typeFilter === "all";
  const configuredType = issueTypeFromFilter(route.typeFilter);
  const exactIssueType = config && configuredType && getConfiguredIssueTypes(config).includes(configuredType)
    ? configuredType : undefined;

  useViewModeSync({
    snapshot, route, setRoute, navActionRef, viewMode, setViewMode,
    focusedIssueId, searchQuery, showAllTypes, exactIssueType,
  });

  const isDetailOpen = Boolean(selectedTask);
  const {
    layoutFrameRef, isResizing, setIsResizing, detailMaximized, setDetailMaximized,
    detailClosing, setDetailClosing,
  } = useDetailPanelLayout(detailWidth, isDetailOpen);
  const isDetailVisible = isDetailOpen || detailClosing;

  useEffect(() => {
    if (!selectedTask || !snapshot) {
      return;
    }
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

  const routeContext = useMemo<IssueSelectionContext>(
    () => resolveRouteContext(route, snapshot, viewMode),
    [route, snapshot, viewMode]
  );

  const fallbackViewMode = route.parentId ? null : "issues";
  const resolvedViewMode = route.parentId
    ? null
    : routeContext.viewMode ?? route.viewMode ?? viewMode ?? fallbackViewMode;
  const typeFilterValue = exactIssueType ? `type:${exactIssueType}` : showAllTypes ? "all" : resolvedViewMode;
  const boardTypeFilter = resolveBoardTypeFilter(showAllTypes, resolvedViewMode);
  const columns = useMemo(() => {
    if (!config) {
      return [];
    }
    return exactIssueType
      ? getStatusColumnsForIssueTypes(config, [exactIssueType])
      : getStatusColumnsForTypeFilter(config, boardTypeFilter);
  }, [config, boardTypeFilter, exactIssueType]);
  const columnError =
    config && columns.length === 0
      ? "default workflow is required to render columns"
      : null;

  useEffect(() => {
    if (showInitiativesInTypeFilter) {
      return;
    }
    if (!snapshot || route.basePath == null) {
      return;
    }
    if (showAllTypes || exactIssueType) {
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
    showAllTypes,
    exactIssueType
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

  const handleTypeFilterChange = (value: string) => {
    if (route.basePath == null) {
      return;
    }
    const exactType = issueTypeFromFilter(value);
    if (exactType && config && getConfiguredIssueTypes(config).includes(exactType)) {
      lastTypeSelectionRef.current = null;
      navigate(buildUrl(`${route.basePath}/${resolvedViewMode ?? "issues"}/`, {
        search: searchQuery || null, typeFilter: value
      }), setRoute, navActionRef);
      return;
    }
    const currentRoute = parseRoute(window.location.pathname, window.location.search);
    const currentShowAll = currentRoute.typeFilter === "all";
    const currentViewMode = currentRoute.parentId
      ? null
      : currentRoute.viewMode ?? viewMode ?? loadStoredViewMode();
    const showAllInPlace = () => {
      replaceCurrentRoute({
        search: searchQuery || null,
        focused: focusedIssueId,
        comment: focusedCommentId,
        typeFilter: "all"
      }, setRoute);
      lastTypeSelectionRef.current = "all";
    };
    if (value === "all") {
      showAllInPlace();
      return;
    }
    const nextMode = value as ViewMode;
    const repeatClick = lastTypeSelectionRef.current === nextMode;
    if (!currentShowAll && currentViewMode === nextMode) {
      if (repeatClick) {
        showAllInPlace();
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

  const handleWikiRouteChange = useCallback(
    (path: string) => {
      const wikiBase = route.basePath ? `${route.basePath}/wiki` : "/wiki";
      const encoded = path ? path.split("/").map(encodeURIComponent).join("/") : "";
      const fullPath = encoded ? `${wikiBase}/${encoded}` : wikiBase;
      navigate(fullPath, setRoute, navActionRef);
    },
    [route.basePath]
  );

  const handlePanelModeChange = (value: string) => {
    const nextMode = value as PanelMode;
    if (panelMode === "wiki" && wikiDirty && nextMode !== "wiki") {
      const proceed = window.confirm("You have unsaved wiki changes. Leave without saving?");
      if (!proceed) {
        return;
      }
    }
    refreshSnapshot();
    setPanelMode(nextMode);
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

  const {
    filterOpen, settingsOpen, activeSidebar, exitingSidebar, sidebarReady, sidebarPhase,
    openSidebar, closeSidebar, toggleSettings, handleSidebarTransitionEnd,
  } = useSidebarPanels();

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
          replaceCurrentRoute({
            search: action.query || null,
            focused: focusedIssueId,
            typeFilter: route.typeFilter
          }, setRoute);
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
        toggleSettings();
        break;
      case "set_setting":
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

  useRealtimeNotifications({
    basePath: route.basePath,
    feed,
    onIssueFocused: (issueId, commentId) => {
      setFocusedIssueId(issueId);
      setFocusedCommentId(commentId);
    },
    onUiControlAction: handleUiControlAction,
  });

  const typeFilterOptions = useMemo(
    () => buildTypeFilterOptions(showInitiativesInTypeFilter),
    [showInitiativesInTypeFilter]
  );
  const panelModeOptions = useMemo(() => buildPanelModeOptions(), [panelMode]);

  const {
    projectLabels, hasVirtualProjects, effectiveEnabledProjects, handleToggleProject,
  } = useProjectFilters(config, enabledProjects, setEnabledProjects);

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

  const { filteredIssues, metricsIssues, hasLocalIssues } = useFilteredIssues({
    issues,
    deferredIssues,
    config,
    resolvedViewMode,
    parentIssue: routeContext.parentIssue,
    parentId: route.parentId,
    focusedIssueId,
    searchQuery,
    enabledProjects,
    effectiveEnabledProjects,
    projectLabels,
    showLocal,
    showShared,
    showAllTypes,
    exactIssueType,
  });

  const handleSelectIssue = useCallback((issue: Issue) => {
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
  }, [route.basePath, route.parentId, route.typeFilter]);

  const viewTrackTransform = useMemo(() => {
    if (panelMode === "board") {
      return "translateX(-25%)";
    }
    if (panelMode === "wiki") {
      return "translateX(-50%)";
    }
    if (panelMode === "metrics") {
      return "translateX(-75%)";
    }
    return "translateX(0)";
  }, [panelMode]);

  const transitionKey = `${resolvedViewMode ?? "none"}`;
  const showLoadingIndicator = loading || !snapshot;

  return (
    <AppShell>
      <ConsoleToolbar
        panelMode={panelMode}
        panelModeOptions={panelModeOptions}
        onPanelModeChange={handlePanelModeChange}
        showLoadingIndicator={showLoadingIndicator}
        searchQuery={searchQuery}
        onSearchChange={handleSearchChange}
        onSearchClear={handleSearchClear}
        showTypeFilterToolbar={showTypeFilterToolbar}
        config={config}
        typeFilterValue={typeFilterValue}
        onTypeFilterChange={handleTypeFilterChange}
        typeFilterOptions={typeFilterOptions}
        filterOpen={filterOpen}
        settingsOpen={settingsOpen}
        onOpenSidebar={openSidebar}
        onCloseSidebar={closeSidebar}
      />

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
          <ConsoleViewTrack
            animate={sidebarReady}
            viewTrackTransform={viewTrackTransform}
            panelMode={panelMode}
            visitedPanelModes={visitedPanelModesRef.current}
            apiBase={apiBase}
            config={config}
            issues={issues}
            filteredIssues={filteredIssues}
            metricsIssues={metricsIssues}
            columns={columns}
            priorityLookup={priorityLookup}
            transitionKey={transitionKey}
            hasLocalIssues={hasLocalIssues}
            projectLabels={projectLabels}
            collapsedColumns={collapsedColumns}
            onToggleCollapse={toggleColumn}
            selectedTask={selectedTask}
            isDetailOpen={isDetailOpen}
            isDetailVisible={isDetailVisible}
            detailMaximized={detailMaximized}
            detailWidth={detailWidth}
            detailNavDirection={detailNavDirection}
            layoutFrameRef={layoutFrameRef}
            setDetailWidth={setDetailWidth}
            setDetailMaximized={setDetailMaximized}
            setIsResizing={setIsResizing}
            setDetailClosing={setDetailClosing}
            onSelectIssue={handleSelectIssue}
            onTaskClose={handleTaskClose}
            onFocus={handleFocus}
            focusedIssueId={focusedIssueId}
            focusedCommentId={focusedCommentId}
            replaceIssueInSnapshot={feed.replaceIssueInSnapshot}
            wikiRoutePath={route.wikiPath}
            onWikiDirtyChange={setWikiDirty}
            onWikiRouteChange={handleWikiRouteChange}
          />
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
            typeConfig={config ?? {}}
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
