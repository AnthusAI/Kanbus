export type WorkflowDefinition = Record<string, string[]>;

export interface ProjectConfig {
  prefix: string;
  hierarchy: string[];
  types: string[];
  workflows: Record<string, WorkflowDefinition>;
  initial_status: string;
  priorities: Record<number, string>;
  default_priority: number;
}

export interface IssueComment {
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
