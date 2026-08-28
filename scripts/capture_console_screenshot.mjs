/**
 * Capture a PNG screenshot of the Kanbus console board using Playwright.
 *
 * Usage: node scripts/capture_console_screenshot.mjs <console-url> <output-path> [mode]
 */

import { createRequire } from "module";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const requireFromConsole = createRequire(join(__dirname, "../apps/console/package.json"));

async function main() {
  const consoleUrl = process.argv[2];
  const outputPath = process.argv[3];
  const appearanceMode = process.argv[4] || "light";
  if (!consoleUrl || !outputPath) {
    console.error(
      "Usage: node scripts/capture_console_screenshot.mjs <console-url> <output-path> [mode]"
    );
    process.exit(1);
  }
  if (appearanceMode !== "light" && appearanceMode !== "dark") {
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

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    await context.addInitScript((mode) => {
      const appearance = {
        theme: "neutral",
        mode,
        font: "sans",
        motion: "full",
      };
      localStorage.setItem("kanbus.console.appearance", JSON.stringify(appearance));
    }, appearanceMode);
    const page = await context.newPage();
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(consoleUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForSelector("[data-testid='board-view']", { timeout: 120000 });
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
