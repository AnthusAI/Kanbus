import type { WikiPageListItem } from "../types/wiki";

export type WikiDirectoryEntry = {
  name: string;
  path: string;
  isDir: boolean;
  title: string;
};

export type WikiRouteResult =
  | { type: "file"; path: string }
  | { type: "directory"; path: string; entries: WikiDirectoryEntry[] }
  | { type: "not_found"; path: string };

function wikiFileStem(name: string): string {
  return name.replace(/\.md$/i, "");
}

/**
 * Remaining wiki pages after a delete.
 *
 * Prefer the server list when it still contains other pages. If that list is
 * empty or unavailable, keep the in-memory pages minus the deleted path.
 */
export function leftoverWikiPagesAfterDelete(
  deletedPath: string,
  knownPages: WikiPageListItem[],
  fetchedPages: WikiPageListItem[] | null
): WikiPageListItem[] {
  const fromMemory = knownPages
    .filter((candidate, index, all) => {
      return (
        candidate.path !== deletedPath
        && all.findIndex((entry) => entry.path === candidate.path) === index
      );
    })
    .slice()
    .sort((left, right) => left.path.localeCompare(right.path));
  if (!fetchedPages) {
    return fromMemory;
  }
  const fromFetch = fetchedPages
    .filter((candidate) => candidate.path !== deletedPath)
    .slice()
    .sort((left, right) => left.path.localeCompare(right.path));
  return fromFetch.length > 0 ? fromFetch : fromMemory;
}

export function resolveWikiRoute(pages: WikiPageListItem[], route: string): WikiRouteResult {
  const normalizedRoute = route.replace(/^\/+/, "").replace(/\/+$/, "");
  const pagePaths = pages.map((page) => page.path);
  const titleByPath = new Map(pages.map((page) => [page.path, page.title]));

  if (pagePaths.includes(normalizedRoute)) {
    return { type: "file", path: normalizedRoute };
  }

  if (normalizedRoute) {
    const indexFallback = `${normalizedRoute}/index.md`;
    if (pagePaths.includes(indexFallback)) {
      return { type: "file", path: indexFallback };
    }
  }

  const prefix = normalizedRoute ? `${normalizedRoute}/` : "";
  const childFiles = normalizedRoute ? pagePaths.filter((pagePath) => pagePath.startsWith(prefix)) : pagePaths;

  if (childFiles.length > 0 || normalizedRoute === "") {
    const entriesMap = new Map<string, WikiDirectoryEntry>();

    for (const file of childFiles) {
      const relativePath = file.slice(prefix.length);
      const parts = relativePath.split("/");
      const name = parts[0];
      const isDir = parts.length > 1;
      const entryPath = normalizedRoute ? `${normalizedRoute}/${name}` : name;

      if (!entriesMap.has(name)) {
        entriesMap.set(name, {
          name,
          path: entryPath,
          isDir,
          title: isDir ? name : (titleByPath.get(file) ?? wikiFileStem(name))
        });
      } else if (isDir) {
        const existing = entriesMap.get(name);
        if (existing) {
          existing.isDir = true;
          existing.title = name;
        }
      }
    }

    const entries = Array.from(entriesMap.values()).sort((left, right) => {
      if (left.isDir !== right.isDir) {
        return left.isDir ? -1 : 1;
      }
      return left.title.localeCompare(right.title);
    });

    return { type: "directory", path: normalizedRoute, entries };
  }

  return { type: "not_found", path: normalizedRoute };
}
