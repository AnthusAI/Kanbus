import { describe, expect, it } from "vitest";
import type { WikiPageListItem } from "../types/wiki";
import {
  leftoverWikiPagesAfterDelete,
  resolveWikiRoute,
  wikiPageToOpenAfterDelete
} from "./wikiRouting";

function pages(...entries: Array<[string, string]>): WikiPageListItem[] {
  return entries.map(([path, title]) => ({ path, title }) as WikiPageListItem);
}

const samplePages = pages(
  ["index.md", "Home"],
  ["guides/setup.md", "Setup"],
  ["guides/deep/notes.md", "Notes"],
  ["about.md", "About"]
);

describe("resolveWikiRoute", () => {
  it("resolves exact file paths", () => {
    expect(resolveWikiRoute(samplePages, "about.md")).toEqual({ type: "file", path: "about.md" });
  });

  it("normalizes slashes", () => {
    expect(resolveWikiRoute(samplePages, "/about.md/")).toEqual({ type: "file", path: "about.md" });
  });

  it("prefers a directory index file", () => {
    const withIndex = pages(["guides/index.md", "Guides"], ["guides/a.md", "A"]);
    expect(resolveWikiRoute(withIndex, "guides")).toEqual({ type: "file", path: "guides/index.md" });
  });

  it("lists the root directory with directories first", () => {
    const result = resolveWikiRoute(samplePages, "");
    expect(result.type).toBe("directory");
    if (result.type === "directory") {
      expect(result.entries.map((entry) => [entry.name, entry.isDir])).toEqual([
        ["guides", true],
        ["about.md", false],
        ["index.md", false]
      ]);
    }
  });

  it("lists nested directories", () => {
    const result = resolveWikiRoute(samplePages, "guides");
    expect(result.type).toBe("directory");
    if (result.type === "directory") {
      expect(result.entries.map((entry) => entry.path)).toEqual(["guides/deep", "guides/setup.md"]);
    }
  });

  it("reports not found", () => {
    expect(resolveWikiRoute(samplePages, "missing")).toEqual({ type: "not_found", path: "missing" });
  });
});

describe("page selection after delete", () => {
  const list = pages(["a.md", "A"], ["b.md", "B"], ["c.md", "C"], ["b.md", "B duplicate"]);

  it("removes the deleted page and duplicates, sorted by path", () => {
    expect(leftoverWikiPagesAfterDelete("b.md", list).map((page) => page.path)).toEqual(["a.md", "c.md"]);
  });

  it("opens the next page by path, else the last one", () => {
    expect(wikiPageToOpenAfterDelete("b.md", list)).toBe("c.md");
    expect(wikiPageToOpenAfterDelete("c.md", list)).toBe("b.md");
  });

  it("returns an empty string when nothing remains", () => {
    expect(wikiPageToOpenAfterDelete("a.md", pages(["a.md", "A"]))).toBe("");
  });
});
