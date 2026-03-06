export interface KanbanStatusDefinition {
  key: string;
  name: string;
  category: string;
  color?: string | null;
}

export interface KanbanCategoryDefinition {
  name: string;
  color?: string | null;
}

export interface KanbanPriorityDefinition {
  name: string;
  color?: string | null;
}

export type KanbanSortPreset =
  | "fifo"
  | "priority-first"
  | "recently-updated";

export type KanbanSortField =
  | "priority"
  | "created_at"
  | "updated_at"
  | "id";

export type KanbanSortDirection = "asc" | "desc";

export interface KanbanSortFieldRule {
  field: KanbanSortField;
  direction: KanbanSortDirection;
}

export type KanbanSortRule = KanbanSortPreset | KanbanSortFieldRule[];

export interface KanbanSortOrder {
  categories?: Record<string, KanbanSortRule>;
  [statusKey: string]:
    | KanbanSortRule
    | Record<string, KanbanSortRule>
    | undefined;
}

export interface KanbanConfig {
  statuses: KanbanStatusDefinition[];
  categories: KanbanCategoryDefinition[];
  priorities: Record<number, KanbanPriorityDefinition>;
  type_colors: Record<string, string>;
  sort_order?: KanbanSortOrder;
}

export interface KanbanIssue {
  id: string;
  title: string;
  type: string;
  status: string;
  priority: number;
  assignee?: string;
  created_at?: string;
  updated_at?: string;
  closed_at?: string;
}
