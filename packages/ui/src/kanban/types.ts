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

export interface KanbanConfig {
  statuses: KanbanStatusDefinition[];
  categories: KanbanCategoryDefinition[];
  priorities: Record<number, KanbanPriorityDefinition>;
  type_colors: Record<string, string>;
}

export interface KanbanIssue {
  id: string;
  title: string;
  type: string;
  status: string;
  priority: number;
  assignee?: string;
  updated_at?: string;
}
