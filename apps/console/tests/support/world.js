import { setWorldConstructor, setDefaultTimeout, BeforeAll, AfterAll, Before, After } from "@cucumber/cucumber";
import { chromium } from "playwright";
import { cp, rm, readFile, writeFile } from "fs/promises";
import path from "path";

const vitePort = process.env.VITE_PORT ?? "5173";
const BASE_URL =
  process.env.CONSOLE_BASE_URL ?? `http://localhost:${vitePort}/`;

let browser;

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;
const fixtureSource = process.env.CONSOLE_UI_FIXTURE_SOURCE;
const configSource = process.env.CONSOLE_UI_CONFIG_SOURCE;
const consoleApiBase = process.env.CONSOLE_API_BASE ?? "http://localhost:5174/api";

async function resetFixture() {
  if (!projectRoot || !fixtureSource || !configSource) {
    return;
  }
  const repositoryRoot = path.dirname(projectRoot);
  await rm(projectRoot, { recursive: true, force: true });
  await rm(path.join(repositoryRoot, "project-local"), { recursive: true, force: true });
  await rm(path.join(repositoryRoot, "virtual"), { recursive: true, force: true });
  await cp(fixtureSource, projectRoot, { recursive: true });
  await writeFile(path.join(repositoryRoot, ".kanbus.yml"), await readFile(configSource));
  await rm(path.join(repositoryRoot, ".kanbus.override.yml"), { force: true });

  for (let attempt = 0; attempt < 5; attempt += 1) {
    const response = await fetch(`${consoleApiBase}/issues?refresh=1`);
    if (response.ok) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error("console fixture reset could not refresh the issue snapshot");
}

setDefaultTimeout(60 * 1000);

class ConsoleWorld {
  constructor() {
    this.page = null;
    this.context = null;
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

Before(async function () {
  await resetFixture();
  this.context = await browser.newContext({
    permissions: ["clipboard-read", "clipboard-write"]
  });
  this.page = await this.context.newPage();
  await this.page.goto(BASE_URL, {
    waitUntil: "domcontentloaded",
    timeout: 60000
  });
  await this.page.evaluate(() => window.localStorage.clear());
  await this.page.reload({ waitUntil: "domcontentloaded" });
});

After(async function () {
  if (this.context) {
    await this.context.close();
    this.context = null;
    this.page = null;
  } else if (this.page) {
    await this.page.close();
  }
  if (this.overridePath) {
    await rm(this.overridePath, { force: true });
    this.overridePath = null;
  }
});
