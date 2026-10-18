import { BeforeAll, AfterAll, Before, After, Given, When, Then, setDefaultTimeout } from "@cucumber/cucumber";
import { chromium, expect } from "@playwright/test";
import { createServer } from "vite";

Given("a configured type filter at width {int} in {string} mode", async function (width, mode) {
  await this.page.setViewportSize({ width, height: 844 });
  await this.page.goto(`${origin}tests/fixture/index.html`);
  await this.page.waitForFunction(() => window.hostReady);
  await this.page.evaluate((mode) => window.renderTypeFilter(mode), mode);
});

Then("the type choices are {string}", async function (choices) {
  await expect(this.page.getByRole("tablist", { name: "Issue type" }).getByRole("tab")).toHaveText(choices.split(", "));
});

When("I choose the issue type {string}", async function (type) {
  await this.page.getByRole("tab", { name: type, exact: true }).click();
});

Then("only filter records of type {string} are displayed", async function (type) {
  const cards = this.page.locator(".issue-card");
  await expect(cards).toHaveCount(type === "article" ? 3 : 1);
  const ids = await cards.evaluateAll((elements) => elements.map((element) => element.dataset.issueId));
  expect(ids.every((id) => id.startsWith(`${type}-`))).toBe(true);
});

Then("all filter records are displayed", async function () {
  await expect(this.page.locator(".issue-card")).toHaveCount(6);
});

Then("the filter has not overflowed the host viewport", async function () {
  expect(await this.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

When("I select issue type {string} with the keyboard and reduced motion", async function (type) {
  await this.page.emulateMedia({ reducedMotion: "reduce" });
  const tab = this.page.getByRole("tab", { name: type, exact: true });
  await tab.focus();
  await tab.press("Enter");
});

Then("the type selector has an accessible selected choice", async function () {
  await expect(this.page.getByRole("tab", { name: "Article", exact: true })).toHaveAttribute("aria-selected", "true");
});

let server;
let browser;
let origin;

When("the host renders a contextual type selector", async function () {
  await this.page.evaluate(() => window.renderUnselectedTypeFilter());
});
Then("no shared type choice is selected", async function () {
  await expect(this.page.getByRole("tablist", { name: "Issue type" }).locator('[aria-selected="true"]')).toHaveCount(0);
});

Given("the shared board consumer {string} at width {int}", async function (consumer, width) {
  this.consumer = consumer;
  this.storageKey = `test.${consumer}.board.v1`;
  await this.page.setViewportSize({ width, height: 844 });
  await this.page.goto(`${origin}tests/fixture/index.html`);
  await this.page.waitForFunction(() => window.hostReady);
  await this.page.evaluate(({ consumer, key }) => window.renderBoardConsumer(consumer, key), { consumer, key: this.storageKey });
});
When("I reload the same shared board consumer", async function () {
  await this.page.reload();
  await this.page.waitForFunction(() => window.hostReady);
  await this.page.evaluate(({ consumer, key }) => window.renderBoardConsumer(consumer, key), { consumer: this.consumer, key: this.storageKey });
});
Then("the collapsed column {string} reclaims its width", async function (name) {
  const column = this.page.getByRole("button", { name: `Expand ${name}`, exact: true }).locator("..");
  expect((await column.boundingBox()).width).toBeLessThanOrEqual(50);
});
When("I select a shared card with the keyboard", async function () {
  const card = this.page.locator('.issue-card[data-issue-id="article-1"]');
  await card.focus();
  await card.press("Enter");
});
Then("the shared detail can close with Escape", async function () {
  await expect(this.page.locator(".kb-issue-detail h2")).toBeFocused();
  await this.page.keyboard.press("Escape");
  await expect(this.page.getByRole("button", { name: "Close issue details" })).toHaveCount(0);
});
Given("a shared board consumer with unavailable storage", async function () {
  await this.page.addInitScript(() => Object.defineProperty(window, "localStorage", { get() { throw new Error("Storage unavailable"); } }));
  await this.page.goto(`${origin}tests/fixture/index.html`);
  await this.page.waitForFunction(() => window.hostReady);
  await this.page.evaluate(() => window.renderBoardConsumer("embedded", "test.blocked"));
});
Given("a shared board consumer with malformed preferences", async function () {
  await this.page.goto(`${origin}tests/fixture/index.html`);
  await this.page.waitForFunction(() => window.hostReady);
  await this.page.evaluate(() => { localStorage.setItem("test.malformed", "broken-json"); window.renderBoardConsumer("embedded", "test.malformed"); });
});

When("the host renders a standalone board", async function () {
  await this.page.evaluate(() => window.renderStandalone());
});
Then("the column {string} can be collapsed", async function (name) {
  await expect(this.page.getByRole("button", { name: `Collapse ${name}`, exact: true })).toBeEnabled();
});
When("I collapse column {string} with the keyboard", async function (name) {
  const button = this.page.getByRole("button", { name: `Collapse ${name}`, exact: true });
  await button.focus();
  await button.press("Enter");
});
When("I expand column {string}", async function (name) {
  await this.page.getByRole("button", { name: `Expand ${name}`, exact: true }).click();
});
Then("column {string} is collapsed", async function (name) {
  const button = this.page.getByRole("button", { name: `Expand ${name}`, exact: true });
  await expect(button).toHaveAttribute("aria-expanded", "false");
  await expect(button.locator("..").locator(".kb-column-scroll")).toHaveCount(0);
});
Then("column {string} is expanded", async function (name) {
  const button = this.page.getByRole("button", { name: `Collapse ${name}`, exact: true });
  await expect(button).toHaveAttribute("aria-expanded", "true");
  await expect(button.locator("..").locator(".kb-column-scroll")).toBeVisible();
});

setDefaultTimeout(15000);

BeforeAll(async () => {
  server = await createServer({ server: { host: "127.0.0.1", port: 0 }, logLevel: "error" });
  await server.listen();
  origin = server.resolvedUrls.local[0];
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
  // Settle Vite's first dependency optimization/reload before the first scenario.
  const warmup = await browser.newPage();
  await warmup.goto(`${origin}tests/fixture/index.html`);
  await warmup.waitForLoadState("networkidle");
  await warmup.close();
});

AfterAll({ timeout: 60000 }, async () => {
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

When("the host renders the organizer board", async function () {
  await this.page.evaluate(() => window.renderOrganizer());
});
Then("the organizer has square outlined cards and folder headers", async function () {
  await expect(this.page.locator('.issue-card').first()).toHaveCSS('border-radius', '0px');
  await expect(this.page.locator('.issue-card').first()).toHaveCSS('border-top-width', '2px');
  await expect(this.page.locator('.kb-column-header').first()).toHaveCSS('clip-path', /polygon/);
  const heights = await this.page.locator('.kb-column').evaluateAll(columns => columns.map(column => column.getBoundingClientRect().height));
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThan(2);
});
Then("the default cards retain their rounded appearance", async function () {
  await expect(this.page.locator('.issue-card').first()).toHaveCSS('border-radius','12px');
});
When("I collapse and reopen the Draft column with the keyboard", async function () {
  await this.page.getByRole('button', {name:'Collapse Draft'}).press('Enter');
  await expect(this.page.getByRole('button', {name:'Expand Draft'})).toHaveAttribute('aria-expanded','false');
  await this.page.getByRole('button', {name:'Expand Draft'}).press('Space');
  await expect(this.page.getByRole('button', {name:'Collapse Draft'})).toHaveAttribute('aria-expanded','true');
});
Then("the activated control has a visible focus indicator", async function () {
  await expect(this.page.getByRole('button',{name:'Collapse Draft'})).toBeFocused();
  await expect(this.page.getByRole('button',{name:'Collapse Draft'})).not.toHaveCSS('outline-style','none');
});
Then("the shared detail panel shows the original title and host fields", async function () {
  const panel=this.page.getByRole('region',{name:'First article details'});
  await expect(panel).toContainText('First article'); await expect(panel).toContainText('Editorial score'); await expect(panel).toContainText('8');
});
When("I close the shared detail panel", async function () { await this.page.getByRole('button',{name:'Close issue details'}).click(); });
Then("focus returns to the selected card", async function () { await expect(this.page.locator('[data-issue-id="article-1"]')).toBeFocused(); });
When(/^the host renders the organizer at width (\d+) in (light|dark) mode$/, async function(width,mode) {
  await this.page.setViewportSize({width:Number(width),height:900});await this.page.emulateMedia({colorScheme:mode,reducedMotion:'reduce'});
  await this.page.evaluate(mode=>window.renderOrganizer(mode),mode);
});
Then("the board starts at its first column without page overflow", async function () {
  await expect(this.page.locator('.kb-grid')).toBeVisible();
  const dimensions=await this.page.evaluate(()=>({scroll:document.querySelector('.kb-grid').scrollLeft,width:document.documentElement.scrollWidth,viewport:innerWidth}));
  expect(dimensions.scroll).toBe(0);expect(dimensions.width).toBeLessThanOrEqual(dimensions.viewport);
});
Then(/^the organizer uses (light|dark) colors$/, async function(mode) {
  await expect(this.page.locator('.kb-theme-organizer')).toHaveCSS('color',mode==='dark'?'rgb(245, 240, 230)':'rgb(16, 22, 34)');
});
Then("issue cards have no reduced-motion animation",async function(){await expect(this.page.locator('.issue-card').first()).toHaveCSS('animation-name','none');});
When("the host renders a narrow default board",async function(){await this.page.setViewportSize({width:375,height:900});await this.page.evaluate(()=>window.renderCollection());});
Then("the board starts at its final column",async function(){await this.page.waitForFunction(()=>{const b=document.querySelector('.kb-grid');return b&&b.scrollLeft>0&&Math.abs(b.scrollLeft-(b.scrollWidth-b.clientWidth))<2;});});
When("the host preserves a board scroll position",async function(){await this.page.evaluate(()=>window.renderOrganizer('light','preserve'));await this.page.locator('.kb-grid').evaluate(b=>b.scrollLeft=40);await this.page.evaluate(()=>window.updateIssue('article-1','review'));});
Then("its scroll position stays unchanged on issue updates",async function(){await this.page.waitForFunction(()=>document.querySelector('.kb-grid')?.scrollLeft===40);});

When(/^the host renders the newsprint board at width (\d+) in (light|dark) mode$/, async function (width, mode) {
  await this.page.setViewportSize({ width: Number(width), height: 900 });
  await this.page.emulateMedia({ colorScheme: mode, reducedMotion: "reduce" });
  await this.page.evaluate((mode) => window.renderNewsprint(mode), mode);
  await expect(this.page.locator(".issue-card").first()).toBeVisible();
});
Then("no element under the newsprint theme has a border radius", async function () {
  const offenders = await this.page.evaluate(() => [...document.querySelectorAll('[data-kanbus-theme="newsprint"], [data-kanbus-theme="newsprint"] *')]
    .filter((element) => ["borderTopLeftRadius", "borderTopRightRadius", "borderBottomLeftRadius", "borderBottomRightRadius"]
      .some((corner) => getComputedStyle(element)[corner] !== "0px")).map((element) => element.className || element.tagName));
  expect(offenders).toEqual([]);
});
Then("a single rule separates adjacent cards in the Draft column", async function () {
  const cards = this.page.locator('[data-column-key="draft"] .issue-card');
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toHaveCSS("border-top-width", "0px");
  await expect(cards.nth(1)).toHaveCSS("border-top-width", "1px");
  await expect(cards.nth(1)).toHaveCSS("border-top-style", "solid");
  const gap = await cards.evaluateAll((elements) => elements[1].getBoundingClientRect().top - elements[0].getBoundingClientRect().bottom);
  expect(gap).toBeLessThanOrEqual(1);
});
Then("the issue id eyebrow sits directly above the headline on {string}", async function (identifier) {
  const card = this.page.locator(`[data-issue-id="${identifier}"]`);
  const distance = await card.evaluate((element) => element.querySelector("h3").getBoundingClientRect().top - element.querySelector(".issue-accent-bar").getBoundingClientRect().bottom);
  expect(distance).toBeGreaterThanOrEqual(0);
  expect(distance).toBeLessThanOrEqual(6);
  await expect(card.locator(".issue-accent-bar")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
});
Then("issue {string} shows a left selection bar and a heavier headline", async function (identifier) {
  const card = this.page.locator(`[data-issue-id="${identifier}"]`);
  await expect(card).toHaveCSS("box-shadow", /inset/);
  await expect(card.locator("h3")).toHaveCSS("font-weight", "800");
});
Then("issue {string} keeps a transparent background", async function (identifier) {
  await expect(this.page.locator(`[data-issue-id="${identifier}"]`)).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
});
Then("the newsprint detail panel is square with a double rule under its heading", async function () {
  const panel = this.page.getByRole("region", { name: "First article details" });
  await expect(panel).toHaveCSS("border-top-left-radius", "0px");
  await expect(panel.locator("h2")).toHaveCSS("border-bottom-style", "double");
});
Then("the excerpt on {string} is clamped to three lines with a More control", async function (identifier) {
  const excerpt = this.page.locator(`[data-issue-id="${identifier}"] .issue-card-excerpt`);
  await expect(excerpt.locator("p")).toHaveCSS("-webkit-line-clamp", "3");
  await expect(excerpt.getByRole("button", { name: "More" })).toHaveAttribute("aria-expanded", "false");
});
When("I press More on the excerpt of {string}", async function (identifier) {
  await this.page.locator(`[data-issue-id="${identifier}"]`).getByRole("button", { name: "More" }).click();
});
Then("the excerpt on {string} is fully shown with a Less control", async function (identifier) {
  const excerpt = this.page.locator(`[data-issue-id="${identifier}"] .issue-card-excerpt`);
  await expect(excerpt).toHaveAttribute("data-expanded", "true");
  await expect(excerpt.getByRole("button", { name: "Less" })).toHaveAttribute("aria-expanded", "true");
});
Then("issue {string} is not selected", async function (identifier) {
  await expect(this.page.locator(`[data-issue-id="${identifier}"]`)).not.toHaveAttribute("data-selected", "true");
  await expect(this.page.getByRole("region", { name: /details$/ })).toHaveCount(0);
});
Then("every newsprint text color has at least 4.5 to 1 contrast against the paper", async function () {
  const ratios = await this.page.evaluate(() => {
    const parse = (value) => value.match(/[\d.]+/g).slice(0, 3).map(Number);
    const luminance = ([r, g, b]) => [r, g, b].map((c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
    const paper = parse(getComputedStyle(document.querySelector('[data-kanbus-theme="newsprint"]')).backgroundColor);
    return [...document.querySelectorAll('[data-kanbus-theme="newsprint"] :is(h3, p, button, .issue-accent-id, .issue-accent-priority, .issue-card-owner)')]
      .filter((element) => element.textContent.trim())
      .map((element) => {
        const [a, b] = [luminance(parse(getComputedStyle(element).color)), luminance(paper)].sort((x, y) => y - x);
        return { name: element.className || element.tagName, ratio: (a + 0.05) / (b + 0.05) };
      });
  });
  expect(ratios.length).toBeGreaterThan(5);
  expect(ratios.filter((entry) => entry.ratio < 4.5)).toEqual([]);
});
