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

When("the host renders a column of {int} issues", async function (count) {
  await this.page.setViewportSize({ width: 1200, height: 900 });
  await this.page.emulateMedia({ reducedMotion: "reduce" });
  await this.page.evaluate((value) => window.renderLargeColumn(value), count);
  await expect(this.page.locator(".issue-card").first()).toBeVisible();
});
Then("the column header shows the count {int}", async function (count) {
  await expect(this.page.locator(".kb-column-header span").last()).toHaveText(String(count));
});
Then("at most {int} issue cards are rendered", async function (limit) {
  expect(await this.page.locator(".issue-card").count()).toBeLessThanOrEqual(limit);
});
When("I scroll the column to its end", async function () {
  const scroller = this.page.locator(".kb-column-scroll");
  await expect.poll(async () => {
    await scroller.evaluate((element) => { element.scrollTop = element.scrollHeight; });
    return this.page.locator('[data-issue-id="bulk-500"]').count();
  }).toBe(1);
});
Then("the issue card {string} is displayed", async function (identifier) {
  await expect(this.page.locator(`.issue-card[data-issue-id="${identifier}"]`)).toBeVisible();
});
When("I select the issue card {string} with the keyboard", async function (identifier) {
  const card = this.page.locator(`.issue-card[data-issue-id="${identifier}"]`);
  await card.focus();
  await card.press("Enter");
});
When("the host replaces every issue with a copy and retitles issue {string} as {string}", async function (identifier, title) {
  await this.page.evaluate(() => window.resetCardRenderCounts());
  await this.page.evaluate(({ identifier, title }) => window.replaceLargeColumnWithCopies(identifier, title), { identifier, title });
  await expect(this.page.locator(`.issue-card[data-issue-id="${identifier}"] h3`)).toHaveText(title);
});
Then("the issue card {string} is rendered again with the title {string}", async function (identifier, title) {
  const counts = await this.page.evaluate(() => window.cardRenderCounts());
  expect(counts[identifier]).toBeGreaterThanOrEqual(1);
  await expect(this.page.locator(`.issue-card[data-issue-id="${identifier}"] h3`)).toHaveText(title);
});
Then("no other issue card is rendered again", async function () {
  const counts = await this.page.evaluate(() => window.cardRenderCounts());
  const others = Object.keys(counts).filter((identifier) => identifier !== "bulk-2");
  expect(others).toEqual([]);
});

const STACKED_ROOT = "[data-layout]";

async function renderStackedBoardAt(world, width, height, settings) {
  await world.page.setViewportSize({ width, height });
  await world.page.evaluate((value) => window.renderStackedBoard(value), { dataset: "articles", ...settings });
  await expect(world.page.locator(STACKED_ROOT)).toHaveCount(1);
}

When("the host renders a stacked board of articles at {int} by {int}", async function (width, height) {
  await renderStackedBoardAt(this, width, height, { dataset: "articles" });
});
When("the host renders a stacked board of {word} data at {int} by {int}", async function (dataset, width, height) {
  await renderStackedBoardAt(this, width, height, { dataset: dataset === "large" ? "large" : "sections" });
});
When("the host renders a stacked board of articles at {int} by {int} with layout {string}", async function (width, height, layout) {
  await renderStackedBoardAt(this, width, height, { layout });
});
When("the host renders a stacked board of articles at {int} by {int} with stackedBelowWidth {int}", async function (width, height, stackedBelowWidth) {
  await renderStackedBoardAt(this, width, height, { stackedBelowWidth });
});
When("the host renders a stacked board of articles at {int} by {int} with columnStateKey {string}", async function (width, height, columnStateKey) {
  await renderStackedBoardAt(this, width, height, { columnStateKey });
});
When("the host renders a stacked board of articles at {int} by {int} with published collapsed by configuration", async function (width, height) {
  await renderStackedBoardAt(this, width, height, { collapsePublishedByConfiguration: true });
});
When("the host renders a stacked board of articles at {int} by {int} with animated motion", async function (width, height) {
  await renderStackedBoardAt(this, width, height, { motionMode: "css" });
});
When("the host renders a stacked board of articles at {int} by {int} with reduced motion", async function (width, height) {
  await this.page.emulateMedia({ reducedMotion: "reduce" });
  await renderStackedBoardAt(this, width, height, { motionMode: "css" });
});
When("the host renders a standalone stacked Board at {int} by {int}", async function (width, height) {
  await renderStackedBoardAt(this, width, height, { component: "board" });
});
When("the viewport becomes {int} by {int}", async function (width, height) {
  await this.page.setViewportSize({ width, height });
});
When("I reload the page and render a stacked board of articles at {int} by {int} with columnStateKey {string}", async function (width, height, columnStateKey) {
  await this.page.reload();
  await this.page.waitForFunction(() => window.hostReady);
  await renderStackedBoardAt(this, width, height, { columnStateKey });
});
When("the host moves stacked issue {string} to status {string}", async function (identifier, status) {
  await this.page.evaluate(({ identifier, status }) => window.updateStackedIssue(identifier, status), { identifier, status });
});

Then("the board layout is {string}", async function (layout) {
  await expect(this.page.locator(STACKED_ROOT)).toHaveAttribute("data-layout", layout);
});
Then("the board sections are {string}", async function (expected) {
  const names = expected.split(", ");
  const headers = this.page.locator(".kb-column-header");
  await expect(headers).toHaveCount(names.length);
  for (let index = 0; index < names.length; index++) {
    await expect(headers.nth(index)).toContainText(names[index]);
  }
});
Then("the board has no horizontal overflow", async function () {
  const overflow = await this.page.evaluate(() => {
    const board = document.querySelector("[data-layout]");
    const elementsPastTheViewport = [...board.querySelectorAll(".issue-card, .kb-column-header, .kb-stacked-scroll")]
      .filter((element) => element.getBoundingClientRect().right > innerWidth + 0.5)
      .map((element) => `${element.tagName}.${element.getAttribute("class")} right=${element.getBoundingClientRect().right}`);
    return { page: document.documentElement.scrollWidth - innerWidth, board: board.scrollWidth - board.clientWidth, elementsPastTheViewport };
  });
  expect(overflow.page).toBeLessThanOrEqual(0);
  expect(overflow.board).toBeLessThanOrEqual(0);
  expect(overflow.elementsPastTheViewport).toEqual([]);
});
Then("the issue cards are stacked vertically", async function () {
  const boxes = await this.page.locator(".issue-card").evaluateAll((cards) => cards.map((card) => card.getBoundingClientRect()));
  expect(boxes.length).toBeGreaterThan(1);
  for (let index = 1; index < boxes.length; index++) {
    expect(boxes[index].top).toBeGreaterThanOrEqual(boxes[index - 1].bottom - 1);
  }
});
Then("the board has not scrolled horizontally", async function () {
  const offsets = await this.page.evaluate(() => [...document.querySelectorAll("[data-layout], [data-layout] *")].map((element) => element.scrollLeft));
  expect(offsets.every((offset) => offset === 0)).toBe(true);
});
Then("the board columns sit side by side", async function () {
  const boxes = await this.page.locator(".kb-column").evaluateAll((columns) => columns.map((column) => column.getBoundingClientRect()));
  expect(boxes.length).toBe(3);
  expect(new Set(boxes.map((box) => Math.round(box.top))).size).toBe(1);
  expect(boxes[1].left).toBeGreaterThan(boxes[0].left);
});
Then("no stacked scroller is rendered", async function () {
  await expect(this.page.locator(".kb-stacked-scroll")).toHaveCount(0);
  await expect(this.page.locator(".kb-column-scroll").first()).toBeVisible();
});
Then("the issue card {string} is selected", async function (identifier) {
  await expect(this.page.locator(`.issue-card[data-issue-id="${identifier}"]`)).toHaveAttribute("data-selected", "true");
});

When("I scroll the stacked board to its end", async function () {
  const scroller = this.page.locator(".kb-stacked-scroll");
  await scroller.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  await this.page.waitForTimeout(200);
  await scroller.evaluate((element) => { element.scrollTop = element.scrollHeight; });
  await this.page.waitForTimeout(200);
});
When("I scroll the stacked board by {int} pixels", async function (pixels) {
  await this.page.locator(".kb-stacked-scroll").evaluate((element, offset) => { element.scrollTop = offset; }, pixels);
  await this.page.waitForTimeout(250);
});
When("I remember the position of the first visible issue card", async function () {
  const remembered = await this.page.locator(".kb-stacked-scroll").evaluate((scroller) => {
    const top = scroller.getBoundingClientRect().top;
    const visible = [...scroller.querySelectorAll(".issue-card")]
      .filter((card) => card.getBoundingClientRect().top > top + 60)
      .sort((left, right) => left.getBoundingClientRect().top - right.getBoundingClientRect().top);
    return { identifier: visible[0].dataset.issueId, offset: visible[0].getBoundingClientRect().top - top };
  });
  this.rememberedOffset = remembered.offset;
  this.rememberedIdentifier = remembered.identifier;
});
When("I select the first visible issue card with the keyboard", async function () {
  const card = this.page.locator(`.issue-card[data-issue-id="${this.rememberedIdentifier}"]`);
  await card.focus();
  await card.press("Enter");
  await expect(this.page.locator(".kb-issue-detail")).toBeVisible();
});
Then("the remembered issue card is displayed", async function () {
  await expect(this.page.locator(`.issue-card[data-issue-id="${this.rememberedIdentifier}"]`)).toHaveCount(1);
});
Then("the remembered issue card is in its remembered position", async function () {
  const card = this.page.locator(`.issue-card[data-issue-id="${this.rememberedIdentifier}"]`);
  await expect(card).toHaveCount(1);
  const offset = await this.page.locator(".kb-stacked-scroll").evaluate(
    (scroller, identifier) => scroller.querySelector(`.issue-card[data-issue-id="${identifier}"]`).getBoundingClientRect().top - scroller.getBoundingClientRect().top,
    this.rememberedIdentifier
  );
  expect(Math.abs(offset - this.rememberedOffset)).toBeLessThanOrEqual(1);
});
When("I close the shared detail panel with Escape", async function () {
  await this.page.locator(".kb-issue-detail h2").focus();
  await this.page.keyboard.press("Escape");
  await expect(this.page.locator(".kb-issue-detail")).toHaveCount(0);
});

Then("a single section header is pinned at the top of the board", async function () {
  const pinnedHeaders = await this.page.locator(".kb-stacked-scroll").evaluate((scroller) => {
    const top = scroller.getBoundingClientRect().top;
    return [...scroller.querySelectorAll(".kb-column-header")]
      .map((header) => header.getBoundingClientRect())
      .filter((box) => Math.abs(box.top - top) <= 1);
  });
  expect(pinnedHeaders.length).toBe(1);
});
Then("the pinned section header belongs to the section of the first visible card", async function () {
  await expect.poll(async () => this.page.locator(".kb-stacked-scroll").evaluate((scroller) => {
    const top = scroller.getBoundingClientRect().top;
    const pinned = [...scroller.querySelectorAll(".kb-column-header")]
      .find((header) => Math.abs(header.getBoundingClientRect().top - top) <= 1);
    const firstCard = [...scroller.querySelectorAll(".issue-card")]
      .filter((card) => card.getBoundingClientRect().bottom > top + 60)
      .sort((left, right) => left.getBoundingClientRect().top - right.getBoundingClientRect().top)[0];
    if (!pinned || !firstCard) return "missing";
    const pinnedSection = pinned.closest("[data-column-key]").dataset.columnKey;
    const cardSection = firstCard.closest("[data-column-key]").dataset.columnKey;
    return pinnedSection === cardSection ? "match" : `${pinnedSection} versus ${cardSection}`;
  })).toBe("match");
});

Then("column {string} is collapsed in the stacked board", async function (name) {
  const button = this.page.getByRole("button", { name: `Expand ${name}`, exact: true });
  await expect(button).toHaveAttribute("aria-expanded", "false");
  const sectionKey = await button.evaluate((element) => element.closest("[data-column-key]").dataset.columnKey);
  await expect(this.page.locator(`.issue-card`).locator(`xpath=ancestor::*[@data-column-key="${sectionKey}"]`)).toHaveCount(0);
});
Then("the stacked section {string} has the vertical text style disabled", async function (name) {
  const button = this.page.getByRole("button", { name: `Expand ${name}`, exact: true });
  await expect(this.page.locator(".kb-column-collapsed")).toHaveCount(0);
  expect(await button.locator(".kb-column-title").evaluate((title) => getComputedStyle(title).writingMode)).toBe("horizontal-tb");
  expect((await button.boundingBox()).width).toBeGreaterThan(200);
});
Then("the chevron of section {string} points {word}", async function (name, direction) {
  const label = direction === "down" ? `Collapse ${name}` : `Expand ${name}`;
  const icon = this.page.getByRole("button", { name: label, exact: true }).locator(".kb-collapse-icon");
  await expect(icon).toHaveAttribute("class", direction === "down" ? /lucide-chevron-down/ : /lucide-chevron-right/);
});
Then("the board is not flipping", async function () {
  await this.page.waitForTimeout(800);
  await expect(this.page.locator(".is-flipping")).toHaveCount(0);
});

When("the host hydrates a server rendered board at {int} by {int}", async function (width, height) {
  this.consoleEntries = [];
  this.page.on("console", (message) => this.consoleEntries.push(`${message.type()}: ${message.text()}`));
  await this.page.setViewportSize({ width, height });
  const hydrationSettings = { columnStateKey: "fixture-hydration-state" };
  const serverModule = await server.ssrLoadModule("/tests/fixture/server-render.tsx");
  const serverRenderedMarkup = serverModule.renderStackedBoardMarkupOnServer(hydrationSettings);
  expect(serverRenderedMarkup).toContain('data-layout="columns"');
  await this.page.evaluate(
    ({ markup, settings }) => window.hydrateStackedBoard(markup, settings),
    { markup: serverRenderedMarkup, settings: hydrationSettings }
  );
});
Then("the hydrated board layout becomes {string}", async function (layout) {
  await expect(this.page.locator("#hydration-root [data-layout]")).toHaveAttribute("data-layout", layout);
  await expect(this.page.locator("#hydration-root .issue-card").first()).toBeVisible();
});
Then("the console reported no hydration warning", async function () {
  const warnings = this.consoleEntries.filter((entry) => /Warning:|hydrat|did not match/i.test(entry));
  expect(warnings).toEqual([]);
});

When("I collapse the pinned section header with the keyboard", async function () {
  const button = this.page.locator(".kb-stacked-sticky-header .kb-column-header");
  await button.focus();
  await button.press("Enter");
});
Then("the header of section {string} is at the top of the board", async function (name) {
  const header = this.page.getByRole("button", { name: `Expand ${name}`, exact: true });
  await expect.poll(async () => {
    const headerTop = (await header.boundingBox()).y;
    const scrollerTop = (await this.page.locator(".kb-stacked-scroll").boundingBox()).y;
    return Math.abs(headerTop - scrollerTop) <= 1;
  }).toBe(true);
});
Then("the header of section {string} shows the count {int}", async function (name, count) {
  const header = this.page.getByRole("button", { name: `Expand ${name}`, exact: true });
  await expect(header.locator("span").last()).toHaveText(String(count));
});
Then("focus is on the header of section {string}", async function (name) {
  await expect(this.page.getByRole("button", { name: `Expand ${name}`, exact: true })).toBeFocused();
});
Then("the remembered issue card is within the viewport", async function () {
  await expect.poll(async () => this.page.locator(`.issue-card[data-issue-id="${this.rememberedIdentifier}"]`).evaluate((card) => {
    const box = card.getBoundingClientRect();
    return box.top >= -1 && box.left >= -1 && box.bottom <= innerHeight + 1 && box.right <= innerWidth + 1;
  })).toBe(true);
});
Then("the issue card {string} is within the viewport", async function (identifier) {
  await expect.poll(async () => this.page.locator(`.issue-card[data-issue-id="${identifier}"]`).evaluate((card) => {
    const box = card.getBoundingClientRect();
    return box.top >= -1 && box.left >= -1 && box.bottom <= innerHeight + 1 && box.right <= innerWidth + 1;
  })).toBe(true);
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

Then("issue {string} keeps a transparent background", async function (identifier) {
  await expect(this.page.locator(`[data-issue-id="${identifier}"]`)).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
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

// Editorial board themes
const themeScope = '[data-kanbus-theme]';
const TOKENS = ["paper", "panel", "sidebar", "ink", "muted", "rule", "accent", "on-accent"];

// Resolves any CSS color (including oklch) to sRGB bytes by painting it on a canvas.
function installColorTools(page) {
  return page.evaluate(() => {
    const context = document.createElement("canvas").getContext("2d", { willReadFrequently: true });
    window.toRgb = (color) => {
      context.clearRect(0, 0, 1, 1);
      context.fillStyle = "#000";
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      return [...context.getImageData(0, 0, 1, 1).data].slice(0, 3);
    };
    const channel = (value) => { const c = value / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    const luminance = ([r, g, b]) => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
    window.contrastBetween = (first, second) => {
      const [high, low] = [luminance(window.toRgb(first)), luminance(window.toRgb(second))].sort((x, y) => y - x);
      return (high + 0.05) / (low + 0.05);
    };
    window.themeToken = (name) => getComputedStyle(document.querySelector("[data-kanbus-theme]")).getPropertyValue(`--kb-theme-${name}`).trim();
  });
}

When(/^the host renders the "([^"]+)" board at width (\d+) in (light|dark) mode$/, async function (theme, width, mode) {
  await this.page.setViewportSize({ width: Number(width), height: 900 });
  await this.page.emulateMedia({ colorScheme: mode, reducedMotion: "reduce" });
  await this.page.evaluate(({ theme, mode }) => window.renderTheme(theme, mode), { theme, mode });
  await expect(this.page.locator(".issue-card").first()).toBeVisible();
  await installColorTools(this.page);
});
When('the host renders the {string} board without a color mode while the visitor prefers light', async function (theme) {
  await this.page.setViewportSize({ width: 1024, height: 900 });
  await this.page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await this.page.evaluate((theme) => window.renderTheme(theme, "system"), theme);
  await expect(this.page.locator(".issue-card").first()).toBeVisible();
  await installColorTools(this.page);
});
When("the visitor switches to prefer dark", async function () {
  await this.page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
});
When("the host renders the {string} board with the accent token overridden", async function (theme) {
  await this.page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await this.page.evaluate((theme) => window.renderTheme(theme, "light", { "--kb-theme-accent": "rgb(200, 10, 20)" }, "article-1"), theme);
  await expect(this.page.locator(".issue-card").first()).toBeVisible();
  await installColorTools(this.page);
});

Then("the theme scope carries the attributes {string} and {string}", async function (theme, mode) {
  const scope = this.page.locator(themeScope);
  await expect(scope).toHaveAttribute("data-kanbus-theme", theme);
  await expect(scope).toHaveAttribute("data-color-mode", mode);
});
Then("the theme scope has no color mode attribute", async function () {
  await expect(this.page.locator(themeScope)).not.toHaveAttribute("data-color-mode");
});
Then("the public color and font tokens all resolve to values", async function () {
  const values = await this.page.evaluate((tokens) => [...tokens, "title-font", "ui-font", "mono-font"].map((name) => [name, window.themeToken(name)]), TOKENS);
  expect(values.filter(([, value]) => !value)).toEqual([]);
});
Then("the board background is the theme paper", async function () {
  const same = await this.page.evaluate(() => {
    const scope = document.querySelector("[data-kanbus-theme]");
    const paper = window.toRgb(window.themeToken("paper"));
    return window.toRgb(getComputedStyle(scope).backgroundColor).join() === paper.join();
  });
  expect(same).toBe(true);
});
Then("the card titles use the title face {string}", async function (face) {
  const family = await this.page.locator(".issue-card h3").first().evaluate((element) => getComputedStyle(element).fontFamily);
  expect(family).toContain(face);
});
Then("the issue id line uses the mono face {string} at 10px", async function (face) {
  const style = await this.page.locator(".issue-card .issue-accent-id").first().evaluate((element) => { const s = getComputedStyle(element); return { family: s.fontFamily, size: s.fontSize }; });
  expect(style.family).toContain(face);
  expect(style.size).toBe("10px");
});
Then("the page paper is light", async function () {
  const [r, g, b] = await this.page.evaluate(() => window.toRgb(getComputedStyle(document.querySelector("[data-kanbus-theme]")).backgroundColor));
  expect((r + g + b) / 3).toBeGreaterThan(200);
});
Then("the page paper is dark", async function () {
  const [r, g, b] = await this.page.evaluate(() => window.toRgb(getComputedStyle(document.querySelector("[data-kanbus-theme]")).backgroundColor));
  expect((r + g + b) / 3).toBeLessThan(60);
});

async function expectContrast(page, pairs) {
  const ratios = await page.evaluate((pairs) => pairs.map(([foreground, background]) => [foreground, background, window.contrastBetween(window.themeToken(foreground), window.themeToken(background))]), pairs);
  expect(ratios.filter(([, , ratio]) => ratio < 4.5)).toEqual([]);
}
async function expectHoverContrast(page, token) {
  const ratio = await page.evaluate((token) => {
    const hover = getComputedStyle(document.querySelector("[data-kanbus-theme]")).getPropertyValue("--card-muted").trim();
    return window.contrastBetween(window.themeToken(token), hover);
  }, token);
  expect(ratio).toBeGreaterThanOrEqual(4.5);
}
Then("ink text has at least 4.5 to 1 contrast against the paper, panel, sidebar and hovered card", async function () {
  await expectContrast(this.page, [["ink", "paper"], ["ink", "panel"], ["ink", "sidebar"]]);
  await expectHoverContrast(this.page, "ink");
});
Then("muted text has at least 4.5 to 1 contrast against the paper, panel, sidebar and hovered card", async function () {
  await expectContrast(this.page, [["muted", "paper"], ["muted", "panel"], ["muted", "sidebar"]]);
  await expectHoverContrast(this.page, "muted");
});
Then("the accent has at least 4.5 to 1 contrast against the paper and panel", async function () {
  await expectContrast(this.page, [["accent", "paper"], ["accent", "panel"]]);
});
Then("text on the accent fill has at least 4.5 to 1 contrast against the accent", async function () {
  await expectContrast(this.page, [["on-accent", "accent"]]);
});
Then("every rendered board text color has at least 4.5 to 1 contrast against the paper", async function () {
  const ratios = await this.page.evaluate(() => {
    const paper = window.themeToken("paper");
    return [...document.querySelectorAll('[data-kanbus-theme] :is(h3, p, button, .issue-accent-id, .issue-accent-priority, .issue-card-owner, .kb-column-header)')]
      .filter((element) => element.textContent.trim())
      .map((element) => ({ name: element.className || element.tagName, ratio: window.contrastBetween(getComputedStyle(element).color, paper) }));
  });
  expect(ratios.length).toBeGreaterThan(5);
  expect(ratios.filter((entry) => entry.ratio < 4.5)).toEqual([]);
});

Then("no element under the theme has a border radius or shadow", async function () {
  const offenders = await this.page.evaluate(() => [...document.querySelectorAll('[data-kanbus-theme] .kb-grid, [data-kanbus-theme] .kb-grid *')]
    .filter((element) => ["borderTopLeftRadius", "borderTopRightRadius", "borderBottomLeftRadius", "borderBottomRightRadius"]
      .some((corner) => getComputedStyle(element)[corner] !== "0px") || (element.matches(".issue-card, .kb-column") && getComputedStyle(element).boxShadow !== "none"))
    .map((element) => element.className || element.tagName));
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
Then("the issue id line sits directly above the headline on {string}", async function (identifier) {
  const card = this.page.locator(`[data-issue-id="${identifier}"]`);
  const distance = await card.evaluate((element) => element.querySelector("h3").getBoundingClientRect().top - element.querySelector(".issue-accent-bar").getBoundingClientRect().bottom);
  expect(distance).toBeGreaterThanOrEqual(0);
  expect(distance).toBeLessThanOrEqual(8);
  await expect(card.locator(".issue-accent-bar")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
});
Then("the Draft column header has a 2px rule and an uppercase label", async function () {
  const header = this.page.locator('[data-column-key="draft"] .kb-column-header');
  await expect(header).toHaveCSS("border-bottom-width", "2px");
  await expect(header).toHaveCSS("text-transform", "uppercase");
  await expect(header).toHaveCSS("font-size", "11px");
});
Then("issue {string} shows a 3px left accent bar", async function (identifier) {
  const bar = await this.page.locator(`[data-issue-id="${identifier}"]`).evaluate((element) => {
    const style = getComputedStyle(element, "::before");
    return { width: style.width, left: style.left, color: window.toRgb(style.backgroundColor), accent: window.toRgb(window.themeToken("accent")) };
  });
  expect(bar.width).toBe("3px");
  expect(bar.left).toBe("0px");
  expect(bar.color).toEqual(bar.accent);
});
Then("the detail panel heading has a 2px rule under it", async function () {
  await expect(this.page.getByRole("region", { name: "First article details" }).locator("h2")).toHaveCSS("border-bottom-width", "2px");
});
Then("the collapsed column {string} is 30px wide", async function (name) {
  const column = this.page.getByRole("button", { name: `Expand ${name}`, exact: true }).locator("..");
  expect((await column.boundingBox()).width).toBe(30);
});
Then("the selection bar color is the overridden accent", async function () {
  const color = await this.page.locator('[data-issue-id="article-1"]').evaluate((element) => getComputedStyle(element, "::before").backgroundColor);
  expect(color).toBe("rgb(200, 10, 20)");
});
Then("the package lists four themes with font families for each", async function () {
  const result = await this.page.evaluate(() => ({ ids: window.kanbusThemeIds, fonts: window.kanbusThemeFonts }));
  expect(result.ids).toEqual(["refined-newsprint", "newspaper-gothic", "night-desk", "broadsheet-green"]);
  for (const id of result.ids) {
    expect(result.fonts[id].length).toBeGreaterThanOrEqual(2);
    for (const font of result.fonts[id]) expect(font.package).toMatch(/^@fontsource(-variable)?\//);
  }
});

When("the host renders the {string} board with issue ids {string} a host formatter", async function (theme, presence) {
  await this.page.setViewportSize({ width: 1400, height: 1000 });
  await this.page.emulateMedia({ colorScheme: "light", reducedMotion: "reduce" });
  await this.page.evaluate(({ theme, withHostFormatter }) => window.renderHostIssueIds(theme, withHostFormatter), { theme, withHostFormatter: presence === "with" });
  await expect(this.page.locator(".issue-card").first()).toBeVisible();
  if (process.env.KANBUS_UI_SCREENSHOT_DIRECTORY) {
    await this.page.screenshot({ path: `${process.env.KANBUS_UI_SCREENSHOT_DIRECTORY}/${theme}-${presence}-host-formatter.png`, fullPage: true });
  }
});

const issueIdSurfaces = {
  card: ".kb-grid .issue-card .issue-accent-id",
  "status tree": "[data-testid='status-tree-id']",
  "detail panel": ".kb-detail-id",
  "task detail heading": ".detail-column .issue-accent-id"
};

Then("the {string} ids read {string}", async function (surface, expected) {
  await expect(this.page.locator(issueIdSurfaces[surface])).toHaveText(expected.split(", "));
});

Then("the {string} ids carry the host format marker", async function (surface) {
  const markers = await this.page.locator(issueIdSurfaces[surface]).evaluateAll((elements) => elements.map((element) => element.dataset.issueIdFormat));
  expect(markers.length).toBeGreaterThan(0);
  expect(markers.every((marker) => marker === "host")).toBe(true);
});

Then("the {string} ids carry no host format marker", async function (surface) {
  const markers = await this.page.locator(issueIdSurfaces[surface]).evaluateAll((elements) => elements.map((element) => element.dataset.issueIdFormat));
  expect(markers.length).toBeGreaterThan(0);
  expect(markers.every((marker) => marker === undefined)).toBe(true);
});

Then("the descendant link is labelled {string}", async function (label) {
  await expect(this.page.getByRole("button", { name: label })).toBeVisible();
});

Then("the host formatted card ids are not uppercase, are monospaced and are not truncated", async function () {
  const styles = await this.page.locator(issueIdSurfaces.card).evaluateAll((elements) => elements.map((element) => {
    const style = getComputedStyle(element);
    return { transform: style.textTransform, family: style.fontFamily, size: style.fontSize, clipped: element.scrollWidth > element.clientWidth };
  }));
  expect(styles.length).toBeGreaterThan(0);
  for (const style of styles) {
    expect(style.transform).toBe("none");
    expect(style.family).toMatch(/Mono/);
    expect(style.size).toBe("10px");
  }
});

Then("the card {string} shows the subtitle {string} under its title", async function (identifier, subtitle) {
  const card = this.page.locator(`.issue-card[data-issue-id="${identifier}"]`);
  const subtitleElement = card.locator(".issue-card-subtitle");
  await expect(subtitleElement).toHaveText(subtitle);
  const follows = await card.evaluate((element) => {
    const heading = element.querySelector("h3");
    return heading?.nextElementSibling?.classList.contains("issue-card-subtitle") ?? false;
  });
  expect(follows).toBe(true);
});
Then("the card {string} has no subtitle element", async function (identifier) {
  await expect(this.page.locator(`.issue-card[data-issue-id="${identifier}"]`)).toHaveCount(1);
  await expect(this.page.locator(`.issue-card[data-issue-id="${identifier}"] .issue-card-subtitle`)).toHaveCount(0);
});
When("the host changes the subtitle of issue {string} to {string}", async function (identifier, subtitle) {
  await this.page.evaluate(({ identifier, subtitle }) => window.updateIssueSubtitle(identifier, subtitle), { identifier, subtitle });
});
