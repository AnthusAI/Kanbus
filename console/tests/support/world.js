import { setWorldConstructor, setDefaultTimeout, BeforeAll, AfterAll, Before, After } from "@cucumber/cucumber";
import { chromium } from "playwright";
import { rm } from "fs/promises";

const vitePort = process.env.VITE_PORT ?? "5173";
const BASE_URL =
  process.env.CONSOLE_BASE_URL ?? `http://localhost:${vitePort}/acme/widgets/`;

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

Before(async function () {
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
