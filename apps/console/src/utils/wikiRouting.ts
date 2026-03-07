export type WikiRouteResult =
  | { type: "file"; path: string }
  | { type: "directory"; path: string; entries: { name: string; path: string; isDir: boolean }[] }
  | { type: "not_found"; path: string };

export function resolveWikiRoute(pages: string[], route: string): WikiRouteResult {
  const normalizedRoute = route.replace(/^\/+/, "").replace(/\/+$/, "");

  // 1. Exact file match
  if (pages.includes(normalizedRoute)) {
    return { type: "file", path: normalizedRoute };
  }

  // 2. Index fallback for directory
  const indexFallback = normalizedRoute ? `${normalizedRoute}/index.md` : "index.md";
  if (pages.includes(indexFallback)) {
    return { type: "file", path: indexFallback };
  }

  // 3. Directory listing
  // A directory exists if there is at least one file that starts with `normalizedRoute/`
  // (or if normalizedRoute is "", any file)
  const prefix = normalizedRoute ? `${normalizedRoute}/` : "";
  const childFiles = normalizedRoute ? pages.filter((p) => p.startsWith(prefix)) : pages;

  if (childFiles.length > 0 || normalizedRoute === "") {
    const entriesMap = new Map<string, { name: string; path: string; isDir: boolean }>();

    for (const file of childFiles) {
      const relativePath = file.slice(prefix.length);
      const parts = relativePath.split("/");
      const name = parts[0];
      const isDir = parts.length > 1;
      const entryPath = normalizedRoute ? `${normalizedRoute}/${name}` : name;

      if (!entriesMap.has(name)) {
        entriesMap.set(name, { name, path: entryPath, isDir });
      } else if (isDir) {
        // If we already have an entry and this one is a directory, make sure we mark it as dir
        // (In case a file and a dir have the same name, which shouldn't happen but just in case)
        entriesMap.get(name)!.isDir = true;
      }
    }

    const entries = Array.from(entriesMap.values()).sort((a, b) => {
      // Sort directories first, then alphabetically
      if (a.isDir !== b.isDir) {
        return a.isDir ? -1 : 1;
      }
      return a.name.localeCompare(b.name);
    });

    return { type: "directory", path: normalizedRoute, entries };
  }

  return { type: "not_found", path: normalizedRoute };
}
