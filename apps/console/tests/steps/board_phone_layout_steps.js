import { When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";

const SCROLL_TOLERANCE_PIXELS = 1;
const MINIMUM_CONTROL_SIZE_PIXELS = 24;
const MINIMUM_SEARCH_FIELD_WIDTH_PIXELS = 60;
const MINIMUM_ISSUE_TYPE_TAB_COUNT = 8;
const CAROUSEL_TRACK_SELECTOR = ".view-track";
const TOOLBAR_TYPE_FILTER_SELECTOR = '[data-testid="console-toolbar"] .kb-type-filter';
const STACKED_SCROLL_SELECTOR = ".kb-stacked-scroll";
const DETAIL_PANEL_SELECTOR = ".detail-column-open";
const DETAIL_CLOSE_SELECTOR = `${DETAIL_PANEL_SELECTOR} button[aria-label="Close"]`;

async function readBoardScrollOffset(page) {
  return page.evaluate((selector) => document.querySelector(selector).scrollTop, STACKED_SCROLL_SELECTOR);
}

async function readViewportSize(page) {
  return page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    height: window.innerHeight
  }));
}

async function readDetailPanelBox(page) {
  const box = await page.locator(DETAIL_PANEL_SELECTOR).boundingBox();
  expect(box, "the open detail panel must have a bounding box").not.toBeNull();
  return box;
}

Then("the board should render stacked", async function () {
  await expect(this.page.locator('[data-layout="stacked"]')).toHaveCount(1);
  await expect(this.page.locator('[data-layout="columns"]')).toHaveCount(0);
});

Then("the board should render in columns", async function () {
  await expect(this.page.locator('[data-layout="columns"]')).toHaveCount(1);
  await expect(this.page.locator('[data-layout="stacked"]')).toHaveCount(0);
});

Then("the board should show more than one column side by side", async function () {
  const columnLefts = await this.page.evaluate(() =>
    [...document.querySelectorAll(".kb-column")].map((column) => Math.round(column.getBoundingClientRect().left))
  );
  expect(new Set(columnLefts).size).toBeGreaterThan(1);
});

Then("the page should not scroll horizontally", async function () {
  const measurement = await this.page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    bodyScrollWidth: document.body.scrollWidth
  }));
  expect(measurement.scrollWidth).toBeLessThanOrEqual(measurement.clientWidth);
  expect(measurement.bodyScrollWidth).toBeLessThanOrEqual(measurement.clientWidth);
});

Then("no element outside the view carousel track should be wider than the viewport", async function () {
  const viewport = await readViewportSize(this.page);
  const oversizedElements = await this.page.evaluate(([viewportWidth, carouselTrackSelector]) =>
    [...document.querySelectorAll("body *")]
      .filter((element) => !element.matches(carouselTrackSelector))
      .filter((element) => element.getBoundingClientRect().width > viewportWidth)
      .map((element) => `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 60)}`),
    [viewport.width, CAROUSEL_TRACK_SELECTOR]
  );
  expect(oversizedElements).toEqual([]);
});

Then("the console toolbar should stay inside the viewport", async function () {
  const viewport = await readViewportSize(this.page);
  const escapingElements = await this.page.evaluate((viewportWidth) => {
    const toolbar = document.querySelector('[data-testid="console-toolbar"]');
    return [toolbar, ...toolbar.querySelectorAll("*")]
      .filter((element) => {
        const rectangle = element.getBoundingClientRect();
        return rectangle.width > 0 && (rectangle.left < -0.5 || rectangle.right > viewportWidth + 0.5);
      })
      .map((element) => `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 60)}`);
  }, viewport.width);
  expect(escapingElements).toEqual([]);
});

Then("the console toolbar should not scroll horizontally", async function () {
  const scrollingElements = await this.page.evaluate(() => {
    const toolbar = document.querySelector('[data-testid="console-toolbar"]');
    return [toolbar, ...toolbar.querySelectorAll("*")]
      .filter((element) => element.scrollWidth > element.clientWidth + 1 && element.clientWidth > 0)
      .map((element) => `${element.tagName.toLowerCase()}.${String(element.className).slice(0, 60)}`);
  });
  expect(scrollingElements).toEqual([]);
});

Then("every console toolbar control should be reachable", async function () {
  const viewport = await readViewportSize(this.page);
  const controlSelectors = [
    '[data-testid="view-toggle-now"]',
    '[data-testid="view-toggle-board"]',
    '[data-testid="view-toggle-wiki"]',
    '[data-testid="view-toggle-metrics"]',
    '[data-testid="search-input"]',
    '[data-testid="filter-button"]',
    '[data-testid="open-settings"]'
  ];
  for (const selector of controlSelectors) {
    const control = this.page.locator(selector);
    await expect(control, selector).toBeVisible();
    const box = await control.boundingBox();
    expect(box.width, `${selector} width`).toBeGreaterThanOrEqual(MINIMUM_CONTROL_SIZE_PIXELS);
    expect(box.height, `${selector} height`).toBeGreaterThanOrEqual(MINIMUM_CONTROL_SIZE_PIXELS - 4);
    expect(box.x, `${selector} left edge`).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width, `${selector} right edge`).toBeLessThanOrEqual(viewport.width);
  }
  const searchField = this.page.locator('[data-testid="search-input-field"]');
  const searchFieldBox = await searchField.boundingBox();
  expect(searchFieldBox.width, "search field width").toBeGreaterThanOrEqual(MINIMUM_SEARCH_FIELD_WIDTH_PIXELS);
  await searchField.fill("reachable");
  await expect(searchField).toHaveValue("reachable");
  await searchField.fill("");
});

Then("every issue type filter tab should be visible", async function () {
  const viewport = await readViewportSize(this.page);
  const tabs = this.page.locator(`${TOOLBAR_TYPE_FILTER_SELECTOR} button[role="tab"]`);
  const tabCount = await tabs.count();
  expect(tabCount).toBeGreaterThanOrEqual(MINIMUM_ISSUE_TYPE_TAB_COUNT);
  const clippedTabs = await this.page.evaluate(([viewportWidth, filterSelector]) => {
    const filter = document.querySelector(filterSelector);
    const filterRectangle = filter.getBoundingClientRect();
    return [...filter.querySelectorAll('button[role="tab"]')]
      .filter((tab) => {
        const rectangle = tab.getBoundingClientRect();
        return (
          rectangle.width === 0 ||
          rectangle.left < filterRectangle.left - 0.5 ||
          rectangle.right > filterRectangle.right + 0.5 ||
          rectangle.left < 0 ||
          rectangle.right > viewportWidth
        );
      })
      .map((tab) => tab.getAttribute("aria-label"));
  }, [viewport.width, TOOLBAR_TYPE_FILTER_SELECTOR]);
  expect(clippedTabs).toEqual([]);
  for (let index = 0; index < tabCount; index += 1) {
    await expect(tabs.nth(index)).toBeInViewport({ ratio: 1 });
  }
});

When("I record the board vertical scroll position", async function () {
  this.recordedBoardScrollOffset = await readBoardScrollOffset(this.page);
});

When("I scroll the board down by {int} pixels", async function (pixels) {
  await this.page.locator(".issue-card").first().waitFor({ timeout: 15000 });
  const offset = await this.page.evaluate(async (distance) => {
    const scroller = document.querySelector(".kb-stacked-scroll");
    scroller.scrollTop = distance;
    await new Promise((resolve) => setTimeout(resolve, 400));
    return scroller.scrollTop;
  }, pixels);
  expect(offset).toBeGreaterThan(0);
});

When("I open the card nearest the middle of the board", async function () {
  const middleCard = await this.page.evaluate(() => {
    const scroller = document.querySelector(".kb-stacked-scroll");
    const scrollerRectangle = scroller.getBoundingClientRect();
    const middle = scrollerRectangle.top + scrollerRectangle.height / 2;
    const candidates = [...document.querySelectorAll(".issue-card")]
      .map((card) => {
        const rectangle = card.getBoundingClientRect();
        return {
          title: card.querySelector("h3").textContent,
          distance: Math.abs(rectangle.top + rectangle.height / 2 - middle),
          fullyVisible: rectangle.top >= scrollerRectangle.top && rectangle.bottom <= scrollerRectangle.bottom
        };
      })
      .filter((candidate) => candidate.fullyVisible)
      .sort((first, second) => first.distance - second.distance);
    return candidates[0] ?? null;
  });
  expect(middleCard, "a fully visible card near the middle of the board").not.toBeNull();
  this.openedCardTitle = middleCard.title;
  await this.page.locator(".issue-card", { hasText: middleCard.title }).first().click();
  await expect(this.page.locator(DETAIL_PANEL_SELECTOR)).toBeVisible();
});

When("I close the detail panel", async function () {
  await this.page.locator(DETAIL_CLOSE_SELECTOR).click();
  await expect(this.page.locator(DETAIL_PANEL_SELECTOR)).toHaveCount(0);
  await this.page.waitForTimeout(600);
});

Then("the detail panel should fill the viewport width", async function () {
  const viewport = await readViewportSize(this.page);
  await this.page.waitForTimeout(600);
  const box = await readDetailPanelBox(this.page);
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
  expect(box.width).toBeGreaterThanOrEqual(viewport.width * 0.9);
});

Then("the detail panel should reach the bottom of the viewport", async function () {
  const viewport = await readViewportSize(this.page);
  const box = await readDetailPanelBox(this.page);
  expect(box.y + box.height).toBeGreaterThanOrEqual(viewport.height - 16);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
});

Then("the detail close control should be inside the viewport", async function () {
  const viewport = await readViewportSize(this.page);
  const closeControl = this.page.locator(DETAIL_CLOSE_SELECTOR);
  await expect(closeControl).toBeVisible();
  await expect(closeControl).toBeInViewport({ ratio: 1 });
  const box = await closeControl.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
});

Then("the detail resizer should not be visible", async function () {
  await expect(this.page.locator(".detail-resizer")).toBeHidden();
});

Then("the detail resizer should be visible", async function () {
  await expect(this.page.locator(".detail-resizer")).toBeVisible();
});

Then("the detail panel should sit beside the board", async function () {
  await this.page.waitForTimeout(600);
  const detailBox = await readDetailPanelBox(this.page);
  const boardBox = await this.page.locator(".layout-slot-board").boundingBox();
  const viewport = await readViewportSize(this.page);
  expect(boardBox.x + boardBox.width).toBeLessThanOrEqual(detailBox.x + 1);
  expect(detailBox.width).toBeLessThan(viewport.width * 0.6);
  expect(boardBox.width).toBeGreaterThan(0);
});

Then("the board vertical scroll position should match the recorded position", async function () {
  const offset = await readBoardScrollOffset(this.page);
  expect(Math.abs(offset - this.recordedBoardScrollOffset)).toBeLessThanOrEqual(SCROLL_TOLERANCE_PIXELS);
});

Then("the task {string} should be visible in the viewport", async function (title) {
  await expect(this.page.locator(".issue-card", { hasText: title }).first()).toBeInViewport({ ratio: 1 });
});

Then("the opened card should be visible in the viewport", async function () {
  await expect(this.page.locator(".issue-card", { hasText: this.openedCardTitle }).first()).toBeInViewport({ ratio: 1 });
});
