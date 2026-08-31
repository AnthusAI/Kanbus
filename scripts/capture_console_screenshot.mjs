/**
 * Capture a PNG screenshot of the Kanbus console board using Playwright.
 *
 * Usage: node scripts/capture_console_screenshot.mjs <console-url> <output-path> <options-json>
 *
 * options-json fields:
 * - appearanceMode: "light" | "dark"
 * - view: "initiatives" | "epics" | "issues" | "all" | null
 * - expandAll: boolean
 * - expand: string[] column status keys
 * - collapse: string[] column status keys
 */

import { createRequire } from "module";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const requireFromConsole = createRequire(join(__dirname, "../apps/console/package.json"));

const VIEW_MODE_STORAGE_KEY = "kanbus.console.viewMode";

function parseOptions(raw) {
  if (!raw) {
    return {
      appearanceMode: "light",
      view: null,
      expandAll: false,
      expand: [],
      collapse: [],
    };
  }
  try {
    const parsed = JSON.parse(raw);
    return {
      appearanceMode: parsed.appearanceMode ?? "light",
      view: parsed.view ?? null,
      expandAll: Boolean(parsed.expandAll),
      expand: Array.isArray(parsed.expand) ? parsed.expand : [],
      collapse: Array.isArray(parsed.collapse) ? parsed.collapse : [],
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`invalid screenshot capture options JSON: ${message}`);
    process.exit(1);
  }
}

function buildConsoleUrl(baseUrl, view) {
  const url = new URL(baseUrl);
  if (view === "initiatives" || view === "epics" || view === "issues") {
    url.pathname = `/${view}/`;
    url.searchParams.delete("type");
    return url.toString();
  }
  if (view === "all") {
    url.searchParams.set("type", "all");
    return url.toString();
  }
  return url.toString();
}

async function applyColumnLayout(page, options) {
  if (options.expandAll) {
    await page.evaluate(() => {
      const isCollapsed = (element) => {
        const style = window.getComputedStyle(element);
        return style.maxWidth === "48px" || style.minWidth === "48px";
      };
      document.querySelectorAll("[data-column-key]").forEach((element) => {
        if (isCollapsed(element)) {
          element.click();
        }
      });
    });
    await page.waitForTimeout(200);
  }

  for (const column of options.expand) {
    await page.evaluate((columnKey) => {
      const element = document.querySelector(`[data-column-key="${columnKey}"]`);
      if (!element) {
        return;
      }
      const style = window.getComputedStyle(element);
      const collapsed = style.maxWidth === "48px" || style.minWidth === "48px";
      if (collapsed) {
        element.click();
      }
    }, column);
    await page.waitForTimeout(100);
  }

  for (const column of options.collapse) {
    await page.evaluate((columnKey) => {
      const element = document.querySelector(`[data-column-key="${columnKey}"]`);
      if (!element) {
        return;
      }
      const style = window.getComputedStyle(element);
      const collapsed = style.maxWidth === "48px" || style.minWidth === "48px";
      if (!collapsed) {
        const header = element.querySelector(".kb-column-header");
        if (header) {
          header.click();
        } else {
          element.click();
        }
      }
    }, column);
    await page.waitForTimeout(100);
  }
}

async function main() {
  const consoleUrl = process.argv[2];
  const outputPath = process.argv[3];
  const options = parseOptions(process.argv[4]);
  if (!consoleUrl || !outputPath) {
    console.error(
      "Usage: node scripts/capture_console_screenshot.mjs <console-url> <output-path> <options-json>"
    );
    process.exit(1);
  }
  if (options.appearanceMode !== "light" && options.appearanceMode !== "dark") {
    console.error("appearance mode must be light or dark");
    process.exit(1);
  }

  let chromium;
  try {
    ({ chromium } = requireFromConsole("playwright"));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(
      `Headless browser capture requires Playwright. Install Chromium with: npx playwright install chromium (${message})`
    );
    process.exit(1);
  }

  const targetUrl = buildConsoleUrl(consoleUrl, options.view);
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    await context.addInitScript(
      ({ appearanceMode, view }) => {
        const appearance = {
          theme: "neutral",
          mode: appearanceMode,
          font: "sans",
          motion: "full",
        };
        localStorage.setItem("kanbus.console.appearance", JSON.stringify(appearance));
        if (view && view !== "all") {
          localStorage.setItem(VIEW_MODE_STORAGE_KEY, view);
        }
      },
      { appearanceMode: options.appearanceMode, view: options.view }
    );
    const page = await context.newPage();
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForSelector("[data-testid='board-view']", { timeout: 120000 });
    await applyColumnLayout(page, options);
    await page.screenshot({ path: outputPath, fullPage: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Headless browser capture failed: ${message}`);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

main();
