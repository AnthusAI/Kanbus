import type { Issue } from "../types/issues";

export type SortPreset =
  | "created-asc"
  | "created-desc"
  | "updated-desc"
  | "priority"
  | "identifier";

export const SORT_PRESETS: { id: SortPreset; label: string }[] = [
  { id: "created-asc", label: "Oldest" },
  { id: "created-desc", label: "Newest" },
  { id: "updated-desc", label: "Updated" },
  { id: "priority", label: "Priority" },
  { id: "identifier", label: "ID" },
];

export const DEFAULT_SORT_PRESET: SortPreset = "created-asc";

function cmpStr(a: string | undefined, b: string | undefined): number {
  const sa = a ?? "";
  const sb = b ?? "";
  if (sa < sb) return -1;
  if (sa > sb) return 1;
  return 0;
}

export function sortIssues(issues: Issue[], preset: SortPreset): Issue[] {
  const sorted = [...issues];
  sorted.sort((a, b) => {
    switch (preset) {
      case "created-asc":
        return cmpStr(a.created_at, b.created_at) || cmpStr(a.id, b.id);
      case "created-desc":
        return cmpStr(b.created_at, a.created_at) || cmpStr(b.id, a.id);
      case "updated-desc":
        return cmpStr(b.updated_at, a.updated_at) || cmpStr(b.id, a.id);
      case "priority":
        return (a.priority - b.priority) || cmpStr(a.created_at, b.created_at) || cmpStr(a.id, b.id);
      case "identifier":
        return cmpStr(a.id, b.id);
    }
  });
  return sorted;
}
