import type { KanbanStatusDefinition } from "./types";

export type WorkflowDefinition = Record<string, string[]>;

export type BoardTypeFilter = "all" | "initiatives" | "epics" | "issues";

export interface WorkflowColumnConfig {
  statuses: KanbanStatusDefinition[];
  workflows: Record<string, WorkflowDefinition>;
  hierarchy: string[];
  types: string[];
}

export function collectWorkflowStatuses(workflow: WorkflowDefinition): Set<string> {
  const statuses = new Set(Object.keys(workflow));
  for (const transitions of Object.values(workflow)) {
    for (const target of transitions) {
      statuses.add(target);
    }
  }
  return statuses;
}

export function getWorkflowForIssueType(
  workflows: Record<string, WorkflowDefinition>,
  issueType: string
): WorkflowDefinition {
  if (issueType in workflows) {
    return workflows[issueType];
  }
  if (!("default" in workflows)) {
    throw new Error("default workflow not defined");
  }
  return workflows.default;
}

export function issueTypesForBoardFilter(
  filter: BoardTypeFilter,
  hierarchy: string[],
  types: string[]
): string[] {
  if (filter === "all") {
    return [];
  }
  if (filter === "initiatives") {
    return ["initiative"];
  }
  if (filter === "epics") {
    return ["epic"];
  }
  const hierarchySet = new Set(hierarchy);
  const excluded = new Set(["initiative", "epic", "sub-task"]);
  const fromHierarchy = hierarchy.filter((entry) => !excluded.has(entry));
  const fromTypes = types.filter(
    (entry) => !excluded.has(entry) && !hierarchySet.has(entry)
  );
  return [...new Set([...fromHierarchy, ...fromTypes])];
}

export function getStatusColumnsForTypeFilter(
  config: WorkflowColumnConfig,
  filter: BoardTypeFilter
): string[] {
  if (filter === "all") {
    return config.statuses.map((status) => status.key);
  }
  const issueTypes = issueTypesForBoardFilter(filter, config.hierarchy, config.types);
  const statusKeys = new Set<string>();
  for (const issueType of issueTypes) {
    const workflow = getWorkflowForIssueType(config.workflows, issueType);
    for (const key of collectWorkflowStatuses(workflow)) {
      statusKeys.add(key);
    }
  }
  return config.statuses
    .map((status) => status.key)
    .filter((key) => statusKeys.has(key));
}
