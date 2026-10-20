import type { Issue } from "../types/issues";

export function reuseUnchangedIssues(
  previousIssuesById: ReadonlyMap<string, Issue>,
  nextIssues: readonly Issue[]
): Map<string, Issue> {
  const nextIssuesById = new Map<string, Issue>();
  for (const issue of nextIssues) {
    if (!issue?.id) {
      continue;
    }
    const previous = previousIssuesById.get(issue.id);
    const unchanged = previous !== undefined
      && previous.updated_at === issue.updated_at
      && JSON.stringify(previous) === JSON.stringify(issue);
    nextIssuesById.set(issue.id, unchanged ? previous : issue);
  }
  return nextIssuesById;
}
