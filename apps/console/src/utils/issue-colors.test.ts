import { describe, expect, it } from "vitest";
import type { ProjectConfig } from "../types/issues";
import { buildStatusCategoryColorVariable, resolveStatusCategoryColorName } from "./issue-colors";

const config = {
  statuses: [
    { key: "open", category: "To do", color: "blue" },
    { key: "doing", category: "Active" },
    { key: "done", category: "Closed" },
    { key: "odd", category: "Weird" }
  ],
  categories: [
    { name: "To do", color: "grey" },
    { name: "Active", color: "bright_blue" },
    { name: "Closed", color: "Green" },
    { name: "Weird", color: "chartreuse" }
  ]
} as unknown as ProjectConfig;

describe("resolveStatusCategoryColorName", () => {
  it("uses the category color, ignoring the status color", () => {
    expect(resolveStatusCategoryColorName(config, "open")).toBe("gray");
  });

  it("resolves aliases and normalizes case", () => {
    expect(resolveStatusCategoryColorName(config, "doing")).toBe("indigo");
    expect(resolveStatusCategoryColorName(config, "done")).toBe("green");
  });

  it("returns null for unknown colors and statuses", () => {
    expect(resolveStatusCategoryColorName(config, "odd")).toBeNull();
    expect(resolveStatusCategoryColorName(config, "missing")).toBeNull();
  });
});

describe("buildStatusCategoryColorVariable", () => {
  it("builds a radix css variable", () => {
    expect(buildStatusCategoryColorVariable(config, "done", "9")).toBe("var(--green-9)");
  });

  it("returns null when the color cannot be resolved", () => {
    expect(buildStatusCategoryColorVariable(config, "odd", "9")).toBeNull();
  });
});
