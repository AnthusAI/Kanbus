import { afterEach, describe, expect, it, vi } from "vitest";
import { stubBrowserWindow } from "./browser-storage-stub";
import {
  DETAIL_WIDTH_STORAGE_KEY,
  ENABLED_PROJECTS_STORAGE_KEY,
  PANEL_MODE_STORAGE_KEY,
  SHOW_LOCAL_STORAGE_KEY,
  VIEW_MODE_STORAGE_KEY,
  loadStoredBoolean,
  loadStoredDetailWidth,
  loadStoredEnabledProjects,
  loadStoredPanelMode,
  loadStoredViewMode
} from "./ui-preferences-storage";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("loadStoredViewMode", () => {
  it("defaults to epics without a window", () => {
    expect(loadStoredViewMode()).toBe("epics");
  });

  it("returns a stored valid mode", () => {
    stubBrowserWindow({ [VIEW_MODE_STORAGE_KEY]: "initiatives" });
    expect(loadStoredViewMode()).toBe("initiatives");
  });

  it("maps the retired tasks mode to issues", () => {
    stubBrowserWindow({ [VIEW_MODE_STORAGE_KEY]: "tasks" });
    expect(loadStoredViewMode()).toBe("issues");
  });

  it("defaults to epics for unknown values", () => {
    stubBrowserWindow({ [VIEW_MODE_STORAGE_KEY]: "bogus" });
    expect(loadStoredViewMode()).toBe("epics");
  });
});

describe("loadStoredPanelMode", () => {
  it("defaults to board", () => {
    stubBrowserWindow();
    expect(loadStoredPanelMode()).toBe("board");
  });

  it("accepts known modes and rejects unknown ones", () => {
    stubBrowserWindow({ [PANEL_MODE_STORAGE_KEY]: "wiki" });
    expect(loadStoredPanelMode()).toBe("wiki");
    stubBrowserWindow({ [PANEL_MODE_STORAGE_KEY]: "other" });
    expect(loadStoredPanelMode()).toBe("board");
  });
});

describe("loadStoredDetailWidth", () => {
  it("defaults to 33", () => {
    stubBrowserWindow();
    expect(loadStoredDetailWidth()).toBe(33);
  });

  it("returns stored widths inside the allowed range", () => {
    stubBrowserWindow({ [DETAIL_WIDTH_STORAGE_KEY]: "45.5" });
    expect(loadStoredDetailWidth()).toBe(45.5);
  });

  it("ignores out of range and non numeric widths", () => {
    stubBrowserWindow({ [DETAIL_WIDTH_STORAGE_KEY]: "10" });
    expect(loadStoredDetailWidth()).toBe(33);
    stubBrowserWindow({ [DETAIL_WIDTH_STORAGE_KEY]: "wide" });
    expect(loadStoredDetailWidth()).toBe(33);
  });
});

describe("loadStoredBoolean", () => {
  it("returns false only for the stored string false, otherwise the fallback", () => {
    stubBrowserWindow({ [SHOW_LOCAL_STORAGE_KEY]: "false" });
    expect(loadStoredBoolean(SHOW_LOCAL_STORAGE_KEY, true)).toBe(false);
    expect(loadStoredBoolean("missing", true)).toBe(true);
    expect(loadStoredBoolean("missing", false)).toBe(false);
  });
});

describe("loadStoredEnabledProjects", () => {
  it("returns null when absent or malformed", () => {
    stubBrowserWindow();
    expect(loadStoredEnabledProjects()).toBeNull();
    stubBrowserWindow({ [ENABLED_PROJECTS_STORAGE_KEY]: "{not json" });
    expect(loadStoredEnabledProjects()).toBeNull();
    stubBrowserWindow({ [ENABLED_PROJECTS_STORAGE_KEY]: "{}" });
    expect(loadStoredEnabledProjects()).toBeNull();
  });

  it("returns a set for a stored array", () => {
    stubBrowserWindow({ [ENABLED_PROJECTS_STORAGE_KEY]: JSON.stringify(["a", "b"]) });
    expect(loadStoredEnabledProjects()).toEqual(new Set(["a", "b"]));
  });
});
