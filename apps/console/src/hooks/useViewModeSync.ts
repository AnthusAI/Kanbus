import { useEffect, useRef, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import type { NavAction, RouteContext, ViewMode } from "../types/console";
import type { IssuesSnapshot } from "../types/issues";
import { navigate } from "../utils/console-route";
import { computeViewModeCounts, selectNonEmptyViewMode } from "../utils/issue-selection";

type ViewModeSyncOptions = {
  snapshot: IssuesSnapshot | null;
  route: RouteContext;
  setRoute: Dispatch<SetStateAction<RouteContext>>;
  navActionRef: MutableRefObject<NavAction>;
  viewMode: ViewMode | null;
  setViewMode: Dispatch<SetStateAction<ViewMode | null>>;
  focusedIssueId: string | null;
  searchQuery: string;
  showAllTypes: boolean;
  exactIssueType: string | undefined;
};

export function useViewModeSync({
  snapshot,
  route,
  setRoute,
  navActionRef,
  viewMode,
  setViewMode,
  focusedIssueId,
  searchQuery,
  showAllTypes,
  exactIssueType,
}: ViewModeSyncOptions): void {
  const viewModeAutoCorrected = useRef(false);

  useEffect(() => {
    if (!snapshot) {
      return;
    }
    viewModeAutoCorrected.current = false;

    if (route.viewMode) {
      return;
    }
    if (showAllTypes || exactIssueType) {
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
  }, [snapshot, focusedIssueId, route.basePath, route.parentId, route.viewMode, searchQuery, viewMode, showAllTypes, exactIssueType]);

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
}
