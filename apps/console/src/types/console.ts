import type { Issue } from "./issues";

export type ViewMode = "initiatives" | "epics" | "issues";
export type PanelMode = "board" | "metrics" | "wiki" | "now";
export type NavAction = "push" | "pop" | "none";
export type SidebarTarget = "filter" | "settings";
export type SidebarPhase = "closed" | "opening" | "open" | "closing";

export type RouteContext = {
  account: string | null;
  project: string | null;
  basePath: string | null;
  viewMode: ViewMode | null;
  issueId: string | null;
  parentId: string | null;
  wikiPath: string | null;
  search: string | null;
  focused: string | null;
  comment: string | null;
  typeFilter: string | null;
  error: string | null;
};

export type IssueSelectionContext = {
  viewMode: ViewMode | null;
  selectedIssue: Issue | null;
  parentIssue: Issue | null;
  error: string | null;
};
