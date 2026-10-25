import { vi } from "vitest";

export function stubBrowserWindow(
  initialStorage: Record<string, string> = {},
  locationSearch = ""
): Map<string, string> {
  const store = new Map<string, string>(Object.entries(initialStorage));
  const localStorage = {
    getItem: (key: string) => (store.has(key) ? (store.get(key) as string) : null),
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    }
  };
  vi.stubGlobal("window", { localStorage, location: { search: locationSearch } });
  return store;
}
