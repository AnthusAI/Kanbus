import type { KanbanIssue } from "./types";

/** A typed comparison against an issue field or a dotted custom field path. */
export interface IssueFieldPredicate {
  field: string;
  operator: "eq" | "lt" | "lte" | "gt" | "gte";
  value: string | number | boolean;
}

/** General Kanbus filters, combined with AND semantics. */
export interface IssueQuery {
  type?: string;
  status?: string;
  assignee?: string;
  label?: string;
  parent?: string;
  search?: string;
  fields?: readonly IssueFieldPredicate[];
}

function fieldValue(issue: KanbanIssue, field: string): unknown {
  let value: unknown = issue;
  for (const segment of field.split(".")) {
    if (!segment || value === null || typeof value !== "object" || Array.isArray(value)
      || !Object.prototype.hasOwnProperty.call(value, segment)) {
      return undefined;
    }
    value = (value as Record<string, unknown>)[segment];
  }
  return value;
}

function compareStrings(left: string, right: string): number {
  const leftPoints = Array.from(left);
  const rightPoints = Array.from(right);
  for (let index = 0; index < Math.min(leftPoints.length, rightPoints.length); index++) {
    const difference = leftPoints[index].codePointAt(0)! - rightPoints[index].codePointAt(0)!;
    if (difference !== 0) return difference;
  }
  return leftPoints.length - rightPoints.length;
}

function matchesField(issue: KanbanIssue, predicate: IssueFieldPredicate): boolean {
  const actual = fieldValue(issue, predicate.field);
  const expected = predicate.value;
  if (typeof actual !== "string" && typeof actual !== "number" && typeof actual !== "boolean") return false;
  if (typeof actual !== typeof expected || actual === undefined || actual === null) return false;
  if (typeof actual === "number" && (!Number.isFinite(actual) || !Number.isFinite(expected))) return false;
  if (predicate.operator === "eq") return actual === expected;

  let order: number;
  if (typeof actual === "number" && typeof expected === "number") {
    order = actual - expected;
  } else if (typeof actual === "string" && typeof expected === "string") {
    order = compareStrings(actual, expected);
  } else {
    return false;
  }
  switch (predicate.operator) {
    case "lt": return order < 0;
    case "lte": return order <= 0;
    case "gt": return order > 0;
    case "gte": return order >= 0;
    default: return false;
  }
}

function matchesSearch(issue: KanbanIssue, search: string): boolean {
  const term = search.toLowerCase();
  if (issue.title.toLowerCase().includes(term) || issue.description?.toLowerCase().includes(term)) return true;
  return issue.comments?.some((comment) => {
    const summary = comment.data?.activity_summary;
    const text = comment.comment_type === "summary" && typeof summary === "string" && summary.trim()
      ? summary : comment.text ?? "";
    return text.toLowerCase().includes(term);
  }) ?? false;
}

/** Filter the supplied records without mutation, reordering, or projection. */
export function filterIssues<Issue extends KanbanIssue>(
  issues: readonly Issue[],
  query: IssueQuery = {}
): Issue[] {
  return issues.filter((issue) => {
    if (query.type !== undefined && issue.type !== query.type) return false;
    if (query.status !== undefined && issue.status !== query.status) return false;
    if (query.assignee !== undefined && issue.assignee !== query.assignee) return false;
    if (query.label !== undefined && !issue.labels?.includes(query.label)) return false;
    if (query.parent !== undefined && !issue.parent?.startsWith(query.parent)) return false;
    if (query.search && !matchesSearch(issue, query.search)) return false;
    return query.fields?.every((predicate) => matchesField(issue, predicate)) ?? true;
  });
}
