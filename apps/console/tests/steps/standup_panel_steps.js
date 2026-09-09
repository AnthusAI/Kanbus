import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";

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
