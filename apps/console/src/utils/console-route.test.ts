import { afterEach, describe, expect, it, vi } from "vitest";
import { stubBrowserWindow } from "./browser-storage-stub";
import { buildUrl, parseQueryParams, parseRoute } from "./console-route";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("parseQueryParams", () => {
  it("extracts non empty parameters", () => {
    expect(parseQueryParams("?search=bug&focused=kbs-1&comment=c1&type=all")).toEqual({
      search: "bug",
      focused: "kbs-1",
      comment: "c1",
      typeFilter: "all"
    });
  });

  it("nulls empty values and unsupported type filters", () => {
    expect(parseQueryParams("?search=&type=bogus")).toEqual({
      search: null,
      focused: null,
      comment: null,
      typeFilter: null
    });
  });

  it("accepts type: prefixed filters", () => {
    expect(parseQueryParams("?type=type:bug").typeFilter).toBe("type:bug");
  });
});

describe("parseRoute local console", () => {
  it("uses the stored view mode at the root", () => {
    stubBrowserWindow({ "kanbus.console.viewMode": "issues" });
    const route = parseRoute("/", "");
    expect(route.viewMode).toBe("issues");
    expect(route.basePath).toBe("");
    expect(route.error).toBeNull();
  });

  it("parses view mode paths", () => {
    stubBrowserWindow();
    expect(parseRoute("/epics", "").viewMode).toBe("epics");
    expect(parseRoute("/initiatives/", "").viewMode).toBe("initiatives");
  });

  it("parses an issue path", () => {
    stubBrowserWindow();
    const route = parseRoute("/issues/kbs-abc123", "");
    expect(route.issueId).toBe("kbs-abc123");
    expect(route.parentId).toBeNull();
  });

  it("parses parent scoped paths", () => {
    stubBrowserWindow();
    const scoped = parseRoute("/issues/kbs-parent/kbs-child", "");
    expect(scoped.parentId).toBe("kbs-parent");
    expect(scoped.issueId).toBe("kbs-child");
    const all = parseRoute("/issues/kbs-parent/all", "");
    expect(all.parentId).toBe("kbs-parent");
    expect(all.issueId).toBeNull();
  });

  it("parses wiki paths and decodes them", () => {
    stubBrowserWindow();
    expect(parseRoute("/wiki/guides/my%20page.md", "").wikiPath).toBe("guides/my page.md");
    expect(parseRoute("/wiki", "").wikiPath).toBe("");
  });

  it("strips a trailing index.html", () => {
    stubBrowserWindow();
    expect(parseRoute("/epics/index.html", "").viewMode).toBe("epics");
  });

  it("reports unsupported local routes", () => {
    stubBrowserWindow();
    expect(parseRoute("/issues/a/b/c", "").error).toBe("Unsupported console route");
  });

  it("carries query parameters", () => {
    stubBrowserWindow();
    const route = parseRoute("/epics", "?search=x&focused=kbs-1");
    expect(route.search).toBe("x");
    expect(route.focused).toBe("kbs-1");
  });
});

describe("parseRoute tenant console", () => {
  it("recognises a bare stage prefix", () => {
    stubBrowserWindow();
    const route = parseRoute("/prod", "");
    expect(route.basePath).toBe("/prod");
    expect(route.error).toBeNull();
  });

  it("requires account and project", () => {
    stubBrowserWindow();
    const route = parseRoute("/acme", "");
    expect(route.basePath).toBeNull();
    expect(route.error).toBe("URL must include /:account/:project");
  });

  it("parses account, project and issue", () => {
    stubBrowserWindow();
    const route = parseRoute("/acme/proj/issues/kbs-1", "");
    expect(route.account).toBe("acme");
    expect(route.project).toBe("proj");
    expect(route.basePath).toBe("/acme/proj");
    expect(route.issueId).toBe("kbs-1");
  });

  it("handles stage prefixed tenant paths", () => {
    stubBrowserWindow();
    const route = parseRoute("/staging/acme/proj/epics", "");
    expect(route.basePath).toBe("/staging/acme/proj");
    expect(route.viewMode).toBe("epics");
  });

  it("uses the stored view mode for a project root", () => {
    stubBrowserWindow({ "kanbus.console.viewMode": "initiatives" });
    expect(parseRoute("/acme/proj", "").viewMode).toBe("initiatives");
  });

  it("parses tenant wiki and parent paths", () => {
    stubBrowserWindow();
    expect(parseRoute("/acme/proj/wiki/a/b", "").wikiPath).toBe("a/b");
    const route = parseRoute("/acme/proj/issues/kbs-p/kbs-c", "");
    expect(route.parentId).toBe("kbs-p");
    expect(route.issueId).toBe("kbs-c");
  });

  it("reports unsupported tenant routes", () => {
    stubBrowserWindow();
    expect(parseRoute("/acme/proj/nonsense", "").error).toBe("Unsupported console route");
  });
});

describe("buildUrl", () => {
  it("returns the bare path without parameters", () => {
    expect(buildUrl("/epics")).toBe("/epics");
  });

  it("encodes provided parameters in a stable order", () => {
    expect(
      buildUrl("/epics", { search: "a b", focused: "kbs-1", comment: "c", typeFilter: "all" })
    ).toBe("/epics?focused=kbs-1&search=a+b&comment=c&type=all");
  });

  it("omits empty parameters", () => {
    expect(buildUrl("/x", { search: "", focused: null })).toBe("/x");
  });
});
