import { useCallback, useEffect, useMemo, useState, type SetStateAction } from "react";
import type { KanbanConfig } from "./types";

export interface BoardColumnStateOptions {
  config?: KanbanConfig;
  columns?: readonly string[];
  /** Host-owned namespace, normally including the workspace/account identity. */
  storageKey?: string;
}

function readColumns(key?: string): string[] | null {
  if (!key || typeof window === "undefined") return null;
  try {
    const stored = JSON.parse(window.localStorage.getItem(key) ?? "null");
    return stored?.version === 1 && Array.isArray(stored.collapsedColumns) &&
      stored.collapsedColumns.every((column: unknown) => typeof column === "string")
      ? stored.collapsedColumns : null;
  } catch { return null; }
}

/** Shared interaction owner for Board and hosts needing external column commands.
 * No transport, schema mutation or global storage key is introduced.
 */
export function useBoardColumnState({ config, columns, storageKey }: BoardColumnStateOptions) {
  // Read after mount so server and first client render use the same configuration defaults.
  const [saved, setSaved] = useState<{ key?: string; value: string[] | null } | null>(null);
  useEffect(() => { setSaved({ key: storageKey, value: readColumns(storageKey) }); }, [storageKey]);
  const stored = saved?.key === storageKey ? saved?.value ?? null : null;
  const defaults = JSON.stringify(config?.statuses.filter(status => status.collapsed).map(status => status.key) ?? []);
  const allowed = JSON.stringify(config?.statuses.map(status => status.key) ?? columns ?? []);
  const [override, setOverride] = useState<{ key?: string; value: string[] } | null>(null);
  const collapsedColumns = useMemo(() => {
    const valid = new Set<string>(JSON.parse(allowed));
    const values = override && override.key === storageKey ? override.value : stored ?? JSON.parse(defaults);
    return new Set<string>((values as string[]).filter(column => valid.has(column)));
  }, [allowed, defaults, override, storageKey, stored]);

  const setCollapsedColumns = useCallback((update: SetStateAction<Set<string>>) => {
    setOverride(previous => {
      const values = previous && previous.key === storageKey ? previous.value : stored ?? JSON.parse(defaults);
      const current = new Set<string>(values);
      const next = typeof update === "function" ? update(current) : update;
      return { key: storageKey, value: [...next] };
    });
  }, [defaults, storageKey, stored]);
  const toggleColumn = useCallback((column: string) => {
    setCollapsedColumns(previous => {
      const next = new Set(previous);
      if (next.has(column)) next.delete(column); else next.add(column);
      return next;
    });
  }, [setCollapsedColumns]);

  const serialized = JSON.stringify([...collapsedColumns]);
  const canPersist = saved !== null && saved.key === storageKey && Boolean(config || columns);
  useEffect(() => {
    if (!storageKey || !canPersist) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify({ version: 1, collapsedColumns: JSON.parse(serialized) }));
    } catch { /* Persistence is optional; interaction still works in restricted browsers. */ }
  }, [storageKey, serialized, canPersist]);
  return { collapsedColumns, setCollapsedColumns, toggleColumn };
}
