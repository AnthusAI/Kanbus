export type WorkflowDefinition = Record<string, string[]>;

export interface PriorityDefinition {
  name: string;
  color?: string | null;
}

export interface ProjectConfig {
  project_directory: string;
  external_projects: string[];
  project_key: string;
  hierarchy: string[];
  types: string[];
  workflows: Record<string, WorkflowDefinition>;
  initial_status: string;
  priorities: Record<number, PriorityDefinition>;
  default_priority: number;
  assignee?: string | null;
  time_zone?: string | null;
  status_colors: Record<string, string>;
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

export interface IssuesSnapshot {
  config: ProjectConfig;
  issues: Issue[];
  updated_at: string;
}
