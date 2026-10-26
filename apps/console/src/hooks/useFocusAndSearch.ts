import { useEffect, useState, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import type { NavAction, RouteContext } from "../types/console";
import type { IssuesSnapshot } from "../types/issues";
import { buildUrl, navigate, parseRoute, replaceCurrentRoute } from "../utils/console-route";
import { resolveIssueByIdentifier } from "../utils/issue-selection";

export type FocusAndSearch = {
  focusedIssueId: string | null;
  setFocusedIssueId: Dispatch<SetStateAction<string | null>>;
  focusedCommentId: string | null;
  setFocusedCommentId: Dispatch<SetStateAction<string | null>>;
  searchQuery: string;
  setSearchQuery: Dispatch<SetStateAction<string>>;
  handleFocus: (issueId: string) => void;
  handleSearchChange: (query: string) => void;
  handleSearchClear: () => void;
  clearFocus: () => void;
};

export function useFocusAndSearch(
  route: RouteContext,
  setRoute: Dispatch<SetStateAction<RouteContext>>,
  navActionRef: MutableRefObject<NavAction>,
  snapshot: IssuesSnapshot | null
): FocusAndSearch {
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

  const handleFocus = (issueId: string) => {
    setFocusedIssueId((prev) => prev === issueId ? null : issueId);
  };

  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
    if (route.basePath != null) {
      replaceCurrentRoute({
        search: query || null,
        focused: focusedIssueId,
        typeFilter: route.typeFilter
      }, setRoute);
    }
  };

  const handleSearchClear = () => {
    setSearchQuery("");
    if (route.basePath != null) {
      replaceCurrentRoute({
        focused: focusedIssueId,
        typeFilter: route.typeFilter
      }, setRoute);
    }
  };

  const clearFocus = () => {
    setFocusedIssueId(null);
    setFocusedCommentId(null);
    if (route.basePath != null) {
      replaceCurrentRoute({
        search: searchQuery || null,
        typeFilter: route.typeFilter
      }, setRoute);
    }
  };

  return {
    focusedIssueId,
    setFocusedIssueId,
    focusedCommentId,
    setFocusedCommentId,
    searchQuery,
    setSearchQuery,
    handleFocus,
    handleSearchChange,
    handleSearchClear,
    clearFocus,
  };
}
