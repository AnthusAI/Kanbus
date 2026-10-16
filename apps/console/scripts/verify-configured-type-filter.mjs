import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "vite";
import react from "@vitejs/plugin-react";
import { chromium, expect } from "@playwright/test";

// Exercise the actual console against bounded in-memory transport fixtures.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const server = await createServer({ configFile: false, root, logLevel: "error",
  cacheDir: path.join(root, "../../tmp/type-filter-vite"),
  plugins: [react()], resolve: { dedupe: ["react", "react-dom"],
    alias: { "@kanbus/ui": path.join(root, "../../packages/ui/dist") } },
  server: { host: "127.0.0.1", port: 0 } });
let browser;
try {
  await server.listen();
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
  const config = { project_directory: "project", project_key: "review", virtual_projects: {},
    hierarchy: ["initiative", "epic", "task", "sub-task"], types: ["story", "article", "reference"],
    workflows: { default: { open: ["done"], done: [] } }, transition_labels: {}, initial_status: "open", default_priority: 2,
    priorities: { 2: { name: "Normal" } }, statuses: [{ key: "open", name: "Open", category: "To do" }, { key: "done", name: "Done", category: "To do", collapsed: true }],
    categories: [{ name: "To do" }], type_colors: {}, beads_compatibility: false };
  const issues = ["initiative", "epic", "task", "story", "article", "reference"].map((type) => ({
    id: `review-${type}`, title: `Synthetic ${type}`, type, status: "open", priority: 2,
    labels: [], comments: [], custom: {}, created_at: "2026-10-15T00:00:00Z", updated_at: "2026-10-15T00:00:00Z" }));
  for (const width of [1440, 390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: "reduce" });
    const errors = [];
    page.on("pageerror", (error) => { errors.push(error.message); console.error("CONSOLE PAGE ERROR", error.message); });
    page.on("console", (message) => { if (message.type() === "error") console.error("CONSOLE ERROR", message.text()); });
    await page.addInitScript(() => localStorage.setItem("kanbus.console.showTypeFilterToolbar", "true"));
    await page.route((url) => url.pathname.startsWith("/api/"), async (route) => {
      const suffix = new URL(route.request().url()).pathname.split("/api/")[1];
      if (route.request().headers().accept === "text/event-stream") {
        await route.fulfill({ status: 200, contentType: "text/event-stream", body: ": synthetic fixture\n\n" });
        return;
      }
      const body = suffix === "config" ? config : suffix === "issues" ? issues : suffix === "auth/bootstrap" ? { mode: "none" } : suffix.endsWith("/events") ? { events: [], total: 0, has_more: false } : {};
      await route.fulfill({ status: suffix === "notifications" ? 404 : 200, contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto(`${server.resolvedUrls.local[0]}issues/?type=all`);
    console.log("Opened console fixture", width);
    const selector = page.getByRole("tablist", { name: "view", exact: true });
    await selector.waitFor();
    const cards = page.locator(".issue-card");
    await expect(cards).toHaveCount(6);
    await expect(page.getByRole("button", { name: "Expand Done", exact: true })).toBeVisible();
    const collapse = page.getByRole("button", { name: "Collapse Open", exact: true });
    await collapse.focus();
    await collapse.press("Enter");
    const expand = page.getByRole("button", { name: "Expand Open", exact: true });
    await expect(expand).toHaveAttribute("aria-expanded", "false");
    await expect(cards).toHaveCount(0);
    assert((await expand.locator("..").boundingBox()).width <= 50);
    await page.reload();
    await expect(expand).toBeVisible();
    await expand.focus();
    await expand.press("Space");
    await expect(cards).toHaveCount(6);
    for (const type of ["Story", "Article", "Reference", "Task", "Epic"]) {
      await selector.getByRole("tab", { name: type, exact: true }).click();
      await expect(cards).toHaveCount(1);
      await expect(cards.first()).toHaveAttribute("data-issue-id", `review-${type.toLowerCase()}`);
    }
    await selector.getByRole("tab", { name: "Epic", exact: true }).click();
    await expect(cards).toHaveCount(6);
    await selector.getByRole("tab", { name: "Article", exact: true }).click();
    await page.reload();
    await expect(selector.getByRole("tab", { name: "Article", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(cards).toHaveCount(1);
    await cards.first().focus();
    await cards.first().press("Enter");
    await expect(page.getByRole("button", { name: "Close", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Close", exact: true }).click();
    await expect(page.getByRole("button", { name: "Close", exact: true })).toHaveCount(0);
    await selector.getByRole("tab", { name: "All", exact: true }).click();
    await expect(cards).toHaveCount(6);
    await selector.getByRole("tab", { name: "Epics", exact: true }).click();
    await expect(cards).toHaveCount(1);
    await expect(cards.first()).toHaveAttribute("data-issue-id", "review-epic");
    assert.deepEqual(errors, []);
    console.log(`PASS: actual console shared collapse/defaults/width/reload/keyboard, selection/detail, configured types, repeat/All and hierarchy view at ${width}px`);
    await page.close();
  }
} finally {
  await browser?.close();
  await server.close();
}
