import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
Given(
  "the issue {string} has an agent conversation event with message {string} claim {string} revision {int} and worktree {string}",
  async function (issueId, message, claim, revision, worktree) {
    const event = {
      schema_version: 1,
      event_id: "router-conversation-details",
      issue_id: issueId,
      event_type: "router.conversation",
      actor_id: "router",
      occurred_at: "2026-09-26T20:00:00Z",
      payload: {
        action: "agent_turn",
        provider: "codex",
        lifecycle: "review",
        message,
        claim_id: claim,
        revision,
        worktree
      }
    };
    await this.page.route(`**/issues/${issueId}/events*`, (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ events: [event], next_before: null })
      })
    );
  }
);

When("I open the issue event history", async function () {
  await this.page.getByRole("button", { name: "Event History" }).click();
});

Then("the conversation event should show the message {string}", async function (text) {
  await expect(this.page.getByTestId("conversation-message")).toHaveText(text);
});

Then("the conversation event should show claim {string}", async function (text) {
  await expect(this.page.getByTestId("conversation-claim")).toHaveText(text);
});

Then("the conversation event should show worktree {string}", async function (text) {
  await expect(this.page.getByTestId("conversation-worktree")).toHaveText(text);
});
