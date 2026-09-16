import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { mkdir, readFile, writeFile } from "fs/promises";
import path from "path";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;
const consoleApiBase = process.env.CONSOLE_API_BASE ?? "http://localhost:5174/api";

function requireProjectRoot() {
  if (!projectRoot) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for standup API tests");
  }
  return projectRoot;
}

async function loadIssue(id) {
  return JSON.parse(await readFile(path.join(requireProjectRoot(), "issues", `${id}.json`), "utf-8"));
}

Given("the browser viewport is {int} by {int}", async function (width, height) {
  await this.page.setViewportSize({ width, height });
});

Given("standup generation is configured to fail", async function () {
  await this.page.route("**/api/standup", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: "standup generation failed" })
    });
  });
});

Given("an issue {string} exists with status {string}", async function (id, status) {
  const issueDirectory = path.join(requireProjectRoot(), "issues");
  await mkdir(issueDirectory, { recursive: true });
  const timestamp = new Date().toISOString();
  await writeFile(path.join(issueDirectory, `${id}.json`), JSON.stringify({
    id,
    title: `Test ${id}`,
    description: "Console standup fixture",
    type: "task",
    status,
    priority: 2,
    assignee: null,
    creator: "fixture",
    labels: [],
    dependencies: [],
    comments: [],
    created_at: timestamp,
    updated_at: timestamp,
    closed_at: null,
    right_now_summary: null,
    right_now_updated_at: null,
    custom: {}
  }, null, 2));
  const response = await fetch(`${consoleApiBase}/issues?refresh=1`);
  expect(response.ok).toBe(true);
});

Given("issue {string} has right now summary {string}", async function (id, summary) {
  const issue = await loadIssue(id);
  issue.right_now_summary = summary;
  issue.right_now_updated_at = issue.updated_at;
  await writeFile(path.join(requireProjectRoot(), "issues", `${id}.json`), JSON.stringify(issue, null, 2));
  const response = await fetch(`${consoleApiBase}/issues?refresh=1`);
  expect(response.ok).toBe(true);
});

When("I open the standup drawer", async function () {
  await this.page.getByTestId("now-standup-button").click();
  await expect(this.page.getByTestId("standup-drawer")).toBeVisible();
});

When("I select the standup profile {string}", async function (profile) {
  await this.page.getByTestId("standup-profile-select").selectOption(profile);
});

When("I generate the standup report", async function () {
  await this.page.getByTestId("standup-generate-button").click();
  await expect(this.page.getByTestId("standup-drawer-busy")).toBeHidden({ timeout: 30000 });
});

When("I copy the standup report", async function () {
  await this.page.getByTestId("standup-copy-button").click();
});

When("I request a standup report from the console API with profile {string}", async function (profile) {
  const response = await fetch(`${consoleApiBase}/standup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile })
  });
  this.standupApiStatus = response.status;
  this.standupApiResponse = await response.json();
});

Then("the now standup button should be visible", async function () {
  await expect(this.page.getByTestId("now-standup-button")).toBeVisible();
});

Then("the standup drawer should be in the viewport", async function () {
  await expect(this.page.getByTestId("standup-drawer")).toBeInViewport();
});

Then("the standup profile select should be in the viewport", async function () {
  await expect(this.page.getByTestId("standup-profile-select")).toBeInViewport();
});

Then("the standup window select should be in the viewport", async function () {
  await expect(this.page.getByTestId("standup-window-select")).toBeInViewport();
});

Then("the standup lookback input should be in the viewport", async function () {
  await expect(this.page.getByTestId("standup-lookback-input")).toBeInViewport();
});

Then("the standup skip weekends checkbox should be in the viewport", async function () {
  await expect(this.page.getByTestId("standup-skip-weekends-checkbox")).toBeInViewport();
});

Then("the standup drawer should show section {string}", async function (sectionName) {
  const section = this.page
    .getByTestId("standup-drawer-section")
    .filter({ has: this.page.getByTestId("standup-drawer-section-title").filter({ hasText: sectionName }) });
  await expect(section).toBeVisible();
});

Then("the standup drawer result should mention {string}", async function (text) {
  await expect(this.page.getByTestId("standup-drawer-result")).toContainText(text);
});

Then("the standup drawer should show error {string}", async function (message) {
  await expect(this.page.getByTestId("standup-drawer-error")).toHaveText(message);
});

Then("the standup drawer should not show a success result", async function () {
  await expect(this.page.getByTestId("standup-drawer-result")).toHaveCount(0);
});

Then("the standup clipboard should contain {string}", async function (text) {
  const clipboardText = await this.page.evaluate(() => navigator.clipboard.readText());
  expect(clipboardText).toContain(text);
});

Then("the standup API response should have profile {string}", function (profile) {
  expect(this.standupApiStatus).toBe(200);
  expect(this.standupApiResponse.profile).toBe(profile);
});

Then("the standup API response should include section {string}", function (sectionName) {
  expect(this.standupApiResponse.sections).toEqual(expect.arrayContaining([
    expect.objectContaining({ name: sectionName })
  ]));
});

Then("the standup API response text should mention {string}", function (text) {
  expect(this.standupApiResponse.text).toContain(text);
});
