import { describe, expect, it } from "vitest";
import type { Issue } from "../types/issues";
import { reuseUnchangedIssues } from "./reuse-unchanged-issues";

function makeIssue(id: string, updatedAt: string, title = id): Issue {
  return { id, title, type: "task", status: "open", priority: 2, updated_at: updatedAt } as Issue;
}

describe("reuseUnchangedIssues", () => {
  it("keeps the previous object for unchanged issues", () => {
    const previous = makeIssue("a", "1");
    const result = reuseUnchangedIssues(new Map([["a", previous]]), [makeIssue("a", "1")]);
    expect(result.get("a")).toBe(previous);
  });

  it("uses the new object when content changed", () => {
    const previous = makeIssue("a", "1");
    const next = makeIssue("a", "1", "renamed");
    expect(reuseUnchangedIssues(new Map([["a", previous]]), [next]).get("a")).toBe(next);
  });

  it("uses the new object when updated_at changed", () => {
    const next = makeIssue("a", "2");
    expect(reuseUnchangedIssues(new Map([["a", makeIssue("a", "1")]]), [next]).get("a")).toBe(next);
  });

  it("drops issues absent from the next list and skips entries without ids", () => {
    const result = reuseUnchangedIssues(new Map([["gone", makeIssue("gone", "1")]]), [
      makeIssue("b", "1"),
      { title: "no id" } as Issue
    ]);
    expect([...result.keys()]).toEqual(["b"]);
  });
});
