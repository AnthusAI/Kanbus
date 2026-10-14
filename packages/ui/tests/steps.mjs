import { BeforeAll, AfterAll, Before, After, Given, When, Then, setDefaultTimeout } from "@cucumber/cucumber";
import { chromium, expect } from "@playwright/test";
import { createServer } from "vite";

let server;
let browser;
let origin;

setDefaultTimeout(15000);

BeforeAll(async () => {
  server = await createServer({ server: { host: "127.0.0.1", port: 0 }, logLevel: "error" });
  await server.listen();
  origin = server.resolvedUrls.local[0];
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
});

AfterAll(async () => {
  await browser?.close();
  await server?.close();
});

Before(async function () {
  this.page = await browser.newPage();
  this.apiRequests = [];
  this.browserErrors = [];
  this.page.on("pageerror", (error) => this.browserErrors.push(error.message));
  this.page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) this.apiRequests.push(request.url());
  });
});

After(async function () {
  await this.page?.close();
  expect(this.browserErrors).toEqual([]);
});

Given("a host application with article and task issues", async function () {
  await this.page.goto(`${origin}tests/fixture/index.html`);
  await this.page.waitForFunction(() => window.hostReady);
  this.hostUrl = this.page.url();
});

When("the host renders an article board", async function () {
  await this.page.evaluate(() => window.renderCollection());
});

When("the host renders a list with query", async function (query) {
  await this.page.evaluate((value) => window.renderCollection(value, "list"), JSON.parse(query));
});

When(/^the host filters articles with query (.+)$/, async function (query) {
  this.matchingIds = await this.page.evaluate((value) => window.filterArticles(value), JSON.parse(query));
});

Then("the matching issue identifiers are {string}", function (expected) {
  expect(this.matchingIds).toEqual(expected ? expected.split(", ") : []);
});

Then("the board columns are {string}", async function (expected) {
  const names = expected.split(", ");
  const columns = this.page.locator(".kb-column-header");
  await expect(columns).toHaveCount(names.length);
  for (let index = 0; index < names.length; index++) {
    await expect(columns.nth(index)).toContainText(names[index]);
  }
});

Then("the displayed issue identifiers are {string}", async function (expected) {
  const identifiers = expected.split(", ");
  await expect(this.page.locator(".issue-card")).toHaveCount(identifiers.length);
  const actual = await this.page.locator(".issue-card").evaluateAll((elements) => elements.map((element) => element.dataset.issueId));
  expect(actual.sort()).toEqual(identifiers.sort());
});

Then("the collection has made no API requests", function () {
  expect(this.apiRequests).toEqual([]);
});

When("I select issue {string} with the keyboard", async function (identifier) {
  await this.page.locator(`[data-issue-id="${identifier}"]`).press("Enter");
});

Then("the host receives the original issue including its custom fields", async function () {
  const result = await this.page.evaluate(() => ({ original: window.selectedOriginal, issue: window.selectedIssue }));
  expect(result.original).toBe(true);
  expect(result.issue.id).toBe("article-1");
  expect(result.issue.custom).toEqual({ score: 8, ready: true });
  expect(result.issue.hostOnlyField).toBe("original record");
});

Then("the host route and outside content remain unchanged", async function () {
  expect(this.page.url()).toBe(this.hostUrl);
  await expect(this.page.locator("#host-navigation")).toHaveText("Host navigation stays here");
});

When("the host supplies issue {string} with status {string}", async function (identifier, status) {
  await this.page.evaluate(({ identifier, status }) => window.updateIssue(identifier, status), { identifier, status });
});

Then("issue {string} appears in column {string}", async function (identifier, status) {
  await expect(this.page.locator(`[data-column-key="${status}"] [data-issue-id="${identifier}"]`)).toHaveCount(1);
});

Then("the collection displays {string}", async function (message) {
  await expect(this.page.getByRole("status")).toHaveText(message);
});

When("the host renders the existing standalone Board directly", async function () {
  await this.page.evaluate(() => window.renderStandalone());
});
