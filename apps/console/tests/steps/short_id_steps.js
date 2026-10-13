import { When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";

function issueCardByIdentity(page, title) {
  return page.locator(".issue-card", { hasText: title });
}

When("I search for {string}", async function (query) {
  await this.page.getByTestId("search-input-field").fill(query);
});

Then(
  "the issue card {string} shows the short ID {string}",
  async function (title, shortId) {
    const card = issueCardByIdentity(this.page, title);
    await expect(card).toBeVisible();
    await expect(card.locator(".issue-accent-id")).toHaveText(shortId);
  }
);
