import { setWorldConstructor, setDefaultTimeout, BeforeAll, AfterAll, Before, After } from "@cucumber/cucumber";
import { chromium } from "playwright";
import { mkdir, readdir, readFile, rm, writeFile } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const vitePort = process.env.VITE_PORT ?? "5173";
const BASE_URL =
  process.env.CONSOLE_BASE_URL ?? `http://localhost:${vitePort}/`;
const consoleRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fixtureProjectRoot = path.join(consoleRoot, "fixtures", "project");
const fixtureConfigPath = path.join(consoleRoot, "fixtures", "kanbus.board-columns.yml");

let browser;

setDefaultTimeout(60 * 1000);

class ConsoleWorld {
  constructor() {
    this.page = null;
    this.overridePath = null;
  }
}

setWorldConstructor(ConsoleWorld);

BeforeAll(async () => {
  browser = await chromium.launch();
});

AfterAll(async () => {
  if (browser) {
    await browser.close();
  }
});

async function waitForRestoredSnapshot(consoleApiBase, expectedIssueIds) {
  const deadline = Date.now() + 10000;
  let lastError = "snapshot refresh did not run";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${consoleApiBase}/issues?refresh=1`);
      if (!response.ok) {
        lastError = `issues refresh ${response.status}`;
      } else {
        const issues = await response.json();
        const ids = new Set(issues.map((issue) => issue.id));
        const missing = [...expectedIssueIds].filter((id) => !ids.has(id));
        const extra = [...ids].filter((id) => !expectedIssueIds.has(id));
        if (missing.length === 0 && extra.length === 0) {
          return;
        }
        lastError = `missing=${missing.join(",")} extra=${extra.join(",")}`;
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`console fixture restore did not settle: ${lastError}`);
}

async function restoreConsoleFixtures() {
  const projectRoot = process.env.CONSOLE_PROJECT_ROOT;
  if (!projectRoot) {
    return;
  }
  const issuesRoot = path.join(projectRoot, "issues");
  const wikiRoot = path.join(projectRoot, "wiki");
  const repoRoot = path.dirname(projectRoot);
  const configPath = process.env.CONSOLE_CONFIG_PATH ?? path.join(repoRoot, ".kanbus.yml");
  const overridePath = path.join(repoRoot, ".kanbus.override.yml");

  await rm(path.join(repoRoot, "project-local"), { recursive: true, force: true });
  await rm(path.join(repoRoot, "virtual"), { recursive: true, force: true });
  await rm(issuesRoot, { recursive: true, force: true });
  await mkdir(issuesRoot, { recursive: true });
  const fixtureIssuesRoot = path.join(fixtureProjectRoot, "issues");
  const fixtureEntries = await readdir(fixtureIssuesRoot);
  const expectedIssueIds = new Set();
  for (const entry of fixtureEntries) {
    if (!entry.endsWith(".json")) {
      continue;
    }
    const contents = await readFile(path.join(fixtureIssuesRoot, entry), "utf-8");
    const issue = JSON.parse(contents);
    expectedIssueIds.add(issue.id);
    await writeFile(path.join(issuesRoot, entry), contents);
  }

  await rm(wikiRoot, { recursive: true, force: true });
  await mkdir(wikiRoot, { recursive: true });
  await rm(overridePath, { force: true });
  const configContents = await readFile(fixtureConfigPath, "utf-8");
  await writeFile(configPath, configContents);

  const consolePort = process.env.CONSOLE_PORT ?? "5174";
  const consoleApiBase =
    process.env.CONSOLE_API_BASE ?? `http://localhost:${consolePort}/api`;
  await fetch(`${consoleApiBase}/config?refresh=1`).catch(() => {});
  await waitForRestoredSnapshot(consoleApiBase, expectedIssueIds);
  await new Promise((resolve) => setTimeout(resolve, 600));
}

Before(async function () {
  await restoreConsoleFixtures();
  this.page = await browser.newPage();
  await this.page.goto(BASE_URL, {
    waitUntil: "domcontentloaded",
    timeout: 60000
  });
  await this.page.evaluate(() => window.localStorage.clear());
  await this.page.reload({ waitUntil: "domcontentloaded" });
});

After(async function () {
  if (this.page) {
    await this.page.close();
  }
  if (this.overridePath) {
    await rm(this.overridePath, { force: true });
    this.overridePath = null;
  }
});
