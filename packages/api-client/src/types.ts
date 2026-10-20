import type { QueryBudgetCost } from "./errors.js";

export interface KanbusComment {
  id?: string;
  author: string;
  text?: string;
  created_at: string;
  comment_type?: string;
  data?: Record<string, unknown>;
}

export interface KanbusIssue {
  id: string;
  title: string;
  type: string;
  status: string;
  priority: number;
  description?: string;
  assignee?: string | null;
  creator?: string;
  parent?: string | null;
  labels?: string[];
  dependencies?: unknown[];
  comments?: KanbusComment[];
  custom?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
  closed_at?: string | null;
}

export interface KanbusIssueWithRevision {
  issue: KanbusIssue;
  revision: string;
}

export interface KanbusIssueWrite extends KanbusIssueWithRevision {
  catalog_pending: boolean;
}

export interface KanbusIssueDeletion {
  deleted: true;
  issue_id: string;
  catalog_pending: boolean;
}

export interface KanbusIssueEvent {
  event_id: string;
  issue_id: string;
  occurred_at: string;
  actor_id?: string;
  [field: string]: unknown;
}

export interface KanbusIssueEvents {
  issue_id: string;
  events: KanbusIssueEvent[];
  next_before: null;
  cost: Record<string, number>;
}

export interface KanbusBoardIssueEntry extends KanbusIssueWithRevision {
  project?: string;
}

export interface KanbusIssuePage {
  issues: KanbusBoardIssueEntry[];
  next_cursor: string | null;
  cost: Record<string, number>;
}

export interface KanbusBoardConfiguration {
  actor_id: string;
  project_key?: string;
  project_directory?: string;
  name?: string;
  hierarchy?: string[];
  types?: string[];
  workflows?: Record<string, Record<string, string[]>>;
  transition_labels?: Record<string, unknown>;
  initial_status?: string;
  priorities?: Record<string, unknown>;
  default_priority?: number;
  assignee?: string | null;
  time_zone?: string | null;
  statuses?: unknown[];
  categories?: unknown[];
  sort_order?: Record<string, unknown>;
  type_colors?: Record<string, string>;
}

export type KanbusFieldOperator = "eq" | "lt" | "lte" | "gt" | "gte";

export interface KanbusFieldPredicate {
  field: string;
  operator: KanbusFieldOperator;
  value: string | number | boolean | null;
}

export interface KanbusIssueQuery {
  type?: string | string[];
  status?: string;
  assignee?: string;
  label?: string;
  parent?: string;
  search?: string;
  sort?: "priority" | "updated_at";
  limit?: number;
  cursor?: string;
  fields?: KanbusFieldPredicate[];
}

export interface KanbusIssueFields {
  title: string;
  type: string;
  status?: string;
  description?: string;
  priority?: number;
  assignee?: string | null;
  parent?: string | null;
  labels?: string[];
  custom?: Record<string, unknown>;
}

export type KanbusIssuePatch = Partial<KanbusIssueFields>;

export interface KanbusWriteOptions {
  operationId: string;
  actor?: string;
}

export interface KanbusRevisionWriteOptions extends KanbusWriteOptions {
  ifMatch: string;
}

export interface KanbusProvisionOptions {
  operationId: string;
  configuration?: string;
}

export interface KanbusBoardLifecycleOptions {
  operationId: string;
  actor?: string;
}

export type KanbusBoardLifecycleResult = Record<string, unknown>;

export type { QueryBudgetCost };
