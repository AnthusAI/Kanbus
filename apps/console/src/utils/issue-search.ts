import type { Issue } from "../types/issues";

/**
 * Normalizes a search query by trimming whitespace and converting to lowercase
 */
export function normalizeSearchQuery(query: string): string {
  return query.trim().toLowerCase();
}

/**
 * Checks if a field contains the search query (null-safe)
 */
export function fieldContains(
  field: string | undefined | null,
  query: string
): boolean {
  if (field == null) {
    return false;
  }
  return field.toLowerCase().includes(query);
}

/**
 * Checks if an issue matches the search query by searching across all relevant fields
 */
export function matchesSearchQuery(issue: Issue, query: string): boolean {
  const normalizedQuery = normalizeSearchQuery(query);

  if (!normalizedQuery) {
    return true;
  }

  // Search standard string fields
  if (
    fieldContains(issue.id, normalizedQuery) ||
    fieldContains(issue.title, normalizedQuery) ||
    fieldContains(issue.description, normalizedQuery) ||
    fieldContains(issue.type, normalizedQuery) ||
    fieldContains(issue.status, normalizedQuery) ||
    fieldContains(issue.assignee, normalizedQuery) ||
    fieldContains(issue.creator, normalizedQuery)
  ) {
    return true;
  }

  // Search in labels array
  if (issue.labels) {
    for (const label of issue.labels) {
      if (fieldContains(label, normalizedQuery)) {
        return true;
      }
    }
  }

  // Search in comments
  if (issue.comments) {
    for (const comment of issue.comments) {
      if (
        fieldContains(comment.author, normalizedQuery) ||
        fieldContains(comment.text, normalizedQuery)
      ) {
        return true;
      }
    }
  }

  // Search in custom fields
  if (issue.custom) {
    for (const value of Object.values(issue.custom)) {
      if (typeof value === "string" && fieldContains(value, normalizedQuery)) {
        return true;
      }
    }
  }

  return false;
}
