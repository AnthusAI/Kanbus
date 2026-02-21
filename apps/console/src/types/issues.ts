export type WorkflowDefinition = Record<string, string[]>;
export type TransitionLabelsDefinition = Record<string, Record<string, Record<string, string>>>;

export interface StatusDefinition {
  key: string;
  name: string;
  category: string;
  color?: string | null;
  collapsed?: boolean;
}

export interface CategoryDefinition {
  name: string;
  color?: string | null;
}

export interface PriorityDefinition {
  name: string;
  color?: string | null;
}

export interface ProjectConfig {
  project_directory: string;
  virtual_projects: Record<string, { path: string }>;
  project_key: string;
  hierarchy: string[];
  types: string[];
  workflows: Record<string, WorkflowDefinition>;
  transition_labels: TransitionLabelsDefinition;
  initial_status: string;
  priorities: Record<number, PriorityDefinition>;
  default_priority: number;
  assignee?: string | null;
  time_zone?: string | null;
  statuses: StatusDefinition[];
  categories: CategoryDefinition[];
  type_colors: Record<string, string>;
  beads_compatibility: boolean;
}

export interface IssueComment {
  id?: string;
  author: string;
  text: string;
  created_at: string;
}

export interface IssueDependency {
  issue_id: string;
  depends_on_id: string;
  type: string;
  created_at: string;
  created_by: string;
}

export interface Issue {
  id: string;
  title: string;
  description?: string;
  type: string;
  status: string;
  priority: number;
  assignee?: string;
  creator?: string;
  parent?: string;
  labels?: string[];
  dependencies?: IssueDependency[];
  comments?: IssueComment[];
  created_at?: string;
  updated_at?: string;
  closed_at?: string;
  custom?: Record<string, unknown>;
}

export type IssueEventType =
  | "issue_created"
  | "state_transition"
  | "field_updated"
  | "comment_added"
  | "comment_updated"
  | "comment_deleted"
  | "dependency_added"
  | "dependency_removed"
  | "issue_deleted"
  | "issue_localized"
  | "issue_promoted";

export interface IssueEvent {
  schema_version: number;
  event_id: string;
  issue_id: string;
  event_type: IssueEventType;
  occurred_at: string;
  actor_id: string;
  payload: Record<string, unknown>;
}

export interface IssueEventsResponse {
  issue_id: string;
  events: IssueEvent[];
  next_before?: string | null;
}

export interface IssuesSnapshot {
  config: ProjectConfig;
  issues: Issue[];
  updated_at: string;
}
