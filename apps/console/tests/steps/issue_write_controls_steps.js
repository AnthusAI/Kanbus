import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { mkdir, writeFile } from "fs/promises";
import path from "path";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;
const consolePort = process.env.CONSOLE_PORT ?? "5174";
const consoleApiBase =
  process.env.CONSOLE_API_BASE ?? `http://localhost:${consolePort}/api`;

function requireProjectRoot() {
  if (!projectRoot) throw new Error("CONSOLE_PROJECT_ROOT is required");
  return projectRoot;
}

async function issueWriteRequest(issueId, route, body) {
  return fetch(`${consoleApiBase}/issues/${encodeURIComponent(issueId)}/${route}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
}

Given("the issue {string} has a blocked router conversation", async (issueId) => {
  const root = requireProjectRoot();
  const eventsRoot = path.join(root, "events");
  await mkdir(eventsRoot, { recursive: true });
  await writeFile(
    path.join(eventsRoot, "router-conversation-blocked.json"),
    JSON.stringify({
      schema_version: 1,
      event_id: "router-conversation-blocked",
      issue_id: `router:${issueId}`,
      event_type: "router.conversation",
      actor_id: "router",
      occurred_at: "2026-09-19T20:00:00Z",
      payload: { lifecycle: "blocked", action: "awaiting_reply" }
    })
  );
});

When(
  "I add a comment through the issue write API for {string} with text {string}",
  async function (issueId, text) {
    this.issueWriteResponse = await issueWriteRequest(issueId, "comments", { text });
    this.issueWritePayload = await this.issueWriteResponse.json();
  }
);

When(
  "I change status through the issue write API for {string} to {string}",
  async function (issueId, status) {
    this.issueWriteResponse = await issueWriteRequest(issueId, "status", { status });
    this.issueWritePayload = await this.issueWriteResponse.json();
  }
);

Then(
  "the issue write API response should be successful with comment {string}",
  async function (text) {
    expect(this.issueWriteResponse.ok).toBe(true);
    expect(this.issueWritePayload.issue.comments.at(-1).text).toBe(text);
  }
);

Then(
  "the issue write API response should be successful with status {string}",
  async function (status) {
    expect(this.issueWriteResponse.ok).toBe(true);
    expect(this.issueWritePayload.issue.status).toBe(status);
  }
);

Then(
  "the issue write API response should fail with status {int} and error containing {string}",
  async function (status, message) {
    expect(this.issueWriteResponse.status).toBe(status);
    expect(this.issueWritePayload.error.toLowerCase()).toContain(message.toLowerCase());
  }
);

Then("the issue write API response should report the agent was resumed", async function () {
  expect(this.issueWritePayload.resumed).toBe(true);
});

Then("the issue write API response should include status {string}", async function (status) {
  expect(this.issueWritePayload.issue.status).toBe(status);
});

// Detail-panel composer steps (comment box, status picker, pending/success/
// error UI states) are intentionally not implemented yet. See the comment
// at the bottom of features/console/issue_write_controls.feature.
