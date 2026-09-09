import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";

Given("the browser viewport is {int} by {int}", async function (width, height) {
  await this.page.setViewportSize({ width, height });
});

When("I open the standup drawer", async function () {
  await this.page.getByTestId("now-standup-button").click();
  await expect(this.page.getByTestId("standup-drawer")).toBeVisible();
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
