import { setWorldConstructor, setDefaultTimeout, BeforeAll, AfterAll, Before, After } from "@cucumber/cucumber";
import { chromium } from "playwright";

const BASE_URL = process.env.CONSOLE_BASE_URL ?? "http://localhost:5173";

let browser;

setDefaultTimeout(60 * 1000);

class ConsoleWorld {
  constructor() {
    this.page = null;
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
  await this.page.addInitScript(() => window.localStorage.clear());
  await this.page.goto(BASE_URL, {
    waitUntil: "domcontentloaded",
    timeout: 60000
  });
});

After(async function () {
  if (this.page) {
    await this.page.close();
  }
});
