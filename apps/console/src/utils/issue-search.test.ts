import { describe, expect, it } from "vitest";
import type { Issue } from "../types/issues";
import { fieldContains, matchesSearchQuery, normalizeSearchQuery } from "./issue-search";

const baseIssue = {
  id: "kbs-1",
  title: "Fix Login Bug",
  type: "task",
  status: "open",
  priority: 2
} as Issue;

describe("normalizeSearchQuery", () => {
  it("trims and lowercases", () => {
    expect(normalizeSearchQuery("  FoO ")).toBe("foo");
  });
});

describe("fieldContains", () => {
  it("is null safe and case insensitive on the field", () => {
    expect(fieldContains(null, "a")).toBe(false);
    expect(fieldContains(undefined, "a")).toBe(false);
    expect(fieldContains("Hello", "ell")).toBe(true);
  });
});

describe("matchesSearchQuery", () => {
  it("matches everything for an empty query", () => {
    expect(matchesSearchQuery(baseIssue, "   ")).toBe(true);
  });

  it("matches standard fields case insensitively", () => {
    expect(matchesSearchQuery(baseIssue, "LOGIN")).toBe(true);
    expect(matchesSearchQuery(baseIssue, "nothing")).toBe(false);
  });

  it("matches labels, comments and string custom fields", () => {
    const issue = {
      ...baseIssue,
      labels: ["backend"],
      comments: [{ author: "ann", text: "needs review" }],
      custom: { note: "special", count: 3 }
    } as unknown as Issue;
    expect(matchesSearchQuery(issue, "backend")).toBe(true);
    expect(matchesSearchQuery(issue, "review")).toBe(true);
    expect(matchesSearchQuery(issue, "ann")).toBe(true);
    expect(matchesSearchQuery(issue, "special")).toBe(true);
    expect(matchesSearchQuery(issue, "3")).toBe(false);
  });
});
