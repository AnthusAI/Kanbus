import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { writeFile } from "fs/promises";
import path from "path";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;

function issueCardLocator(page, title) {
  return page.locator(".issue-card", { hasText: title });
}

Given("the console is open", async function () {
  await expect(this.page.getByTestId("open-settings")).toBeVisible();
});

Given("local storage is cleared", async function () {
  await this.page.evaluate(() => window.localStorage.clear());
});

When("the console is reloaded", async function () {
  await this.page.reload({ waitUntil: "domcontentloaded" });
});

When("I switch to the {string} tab", async function (tabName) {
  await this.page.getByRole("tab", { name: tabName }).click();
});

When("I open the task {string}", async function (title) {
  await issueCardLocator(this.page, title).click();
});

When("a new task issue named {string} is added", async function (title) {
  if (!projectRoot) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for SSE tests");
  }
  const issueId = "tsk-task-2";
  const issue = {
    id: issueId,
    title,
    description: "Generated during test",
    type: "task",
    status: "open",
    priority: 2,
    assignee: "dev@example.com",
    creator: "System",
    labels: [],
    dependencies: [],
    comments: []
  };
  const filePath = path.join(projectRoot, "issues", `${issueId}.json`);
  await writeFile(filePath, JSON.stringify(issue, null, 2));
});

Then("I should see the issue {string}", async function (title) {
  await expect(issueCardLocator(this.page, title)).toBeVisible();
});

Then("I should not see the issue {string}", async function (title) {
  await expect(issueCardLocator(this.page, title)).toHaveCount(0);
});

Then("the {string} tab should be selected", async function (tabName) {
  await expect(this.page.getByRole("tab", { name: tabName })).toHaveAttribute(
    "aria-selected",
    "true"
  );
});

When("I open settings", async function () {
  await this.page.getByTestId("open-settings").click();
  await expect(this.page.getByTestId("settings-panel")).toBeVisible();
});

When("I set the theme to {string}", async function (theme) {
  await this.page.locator(`[data-selector=\"theme\"][data-option=\"${theme}\"]`).click();
});

When("I set the mode to {string}", async function (mode) {
  await this.page.locator(`[data-selector=\"mode\"][data-option=\"${mode}\"]`).click();
});

When("I set the typeface to {string}", async function (font) {
  await this.page.locator(`[data-selector=\"font\"][data-option=\"${font}\"]`).click();
});

When("I set motion to {string}", async function (motion) {
  await this.page.locator(`[data-selector=\"motion\"][data-option=\"${motion}\"]`).click();
});

Then("the theme should be {string}", async function (theme) {
  const stored = await this.page.evaluate(() => window.localStorage.getItem("taskulus.console.appearance"));
  expect(stored).not.toBeNull();
  const parsed = JSON.parse(stored);
  expect(parsed.theme).toBe(theme);
});

Then("the mode should be {string}", async function (mode) {
  const stored = await this.page.evaluate(() => window.localStorage.getItem("taskulus.console.appearance"));
  expect(stored).not.toBeNull();
  const parsed = JSON.parse(stored);
  expect(parsed.mode).toBe(mode);
});

Then("the typeface should be {string}", async function (font) {
  const stored = await this.page.evaluate(() => window.localStorage.getItem("taskulus.console.appearance"));
  expect(stored).not.toBeNull();
  const parsed = JSON.parse(stored);
  expect(parsed.font).toBe(font);
});

Then("the motion mode should be {string}", async function (motion) {
  const stored = await this.page.evaluate(() => window.localStorage.getItem("taskulus.console.appearance"));
  expect(stored).not.toBeNull();
  const parsed = JSON.parse(stored);
  expect(parsed.motion).toBe(motion);
  const datasetMotion = await this.page.evaluate(() => document.documentElement.dataset.motion);
  expect(datasetMotion).toBe(motion);
});

Then("I should see the sub-task {string}", async function (title) {
  await expect(this.page.locator("text=Sub-tasks")).toBeVisible();
  await expect(this.page.locator(".issue-card", { hasText: title })).toBeVisible();
});
