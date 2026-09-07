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

function uniqueWikiPagesSortedByPath(pages: WikiPageListItem[]): WikiPageListItem[] {
  return pages
    .filter((candidate, index, all) => {
      return all.findIndex((entry) => entry.path === candidate.path) === index;
    })
    .slice()
    .sort((left, right) => left.path.localeCompare(right.path));
}

/**
 * Remaining wiki pages after a delete.
 *
 * Uses the remaining-page list returned by the delete response. The deleted
 * path is excluded if it is still present in that list.
 */
export function leftoverWikiPagesAfterDelete(
  deletedPath: string,
  remainingPages: WikiPageListItem[]
): WikiPageListItem[] {
  return uniqueWikiPagesSortedByPath(remainingPages).filter((candidate) => {
    return candidate.path !== deletedPath;
  });
}

/**
 * Wiki path to open after deleting a page.
 *
 * Opens the next remaining page after the deleted path. If the deleted page
 * was last, opens the previous remaining page. If none remain, opens the
 * wiki home directory.
 */
export function wikiPageToOpenAfterDelete(
  deletedPath: string,
  remainingPages: WikiPageListItem[]
): string {
  const leftoverPages = leftoverWikiPagesAfterDelete(deletedPath, remainingPages);
  if (leftoverPages.length === 0) {
    return "";
  }
  const nextPage = leftoverPages.find((page) => page.path > deletedPath);
  if (nextPage) {
    return nextPage.path;
  }
  return leftoverPages[leftoverPages.length - 1].path;
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
