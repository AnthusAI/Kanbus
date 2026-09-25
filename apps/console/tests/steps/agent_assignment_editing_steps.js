import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { readFile, writeFile } from "fs/promises";
import path from "path";
import yaml from "js-yaml";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;
const consolePort = process.env.CONSOLE_PORT ?? "5174";
const consoleApiBase =
  process.env.CONSOLE_API_BASE ?? `http://localhost:${consolePort}/api`;

function requireProjectRoot() {
  if (!projectRoot) throw new Error("CONSOLE_PROJECT_ROOT is required");
  return projectRoot;
}

async function assignmentRequest(issueId, body) {
  return fetch(`${consoleApiBase}/issues/${encodeURIComponent(issueId)}/assignment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
}

Given(
  "the Kanbus configuration has a router with class {string} using provider {string}",
  async (className, providerName) => {
    const configPath = path.join(requireProjectRoot(), "..", ".kanbus.yml");
    const config = yaml.load(await readFile(configPath, "utf-8")) ?? {};
    config.router = {
      workflow: {
        pending: "open",
        active: "in_progress",
        review: "copy_writing",
        blocked: "blocked",
        terminal: ["closed"]
      },
      limits: { project_wip: 3, review_wip: 2 },
      providers: { [providerName]: { adapter: "codex" } },
      classes: { [className]: { providers: [providerName] } }
    };
    await writeFile(configPath, yaml.dump(config, { sortKeys: false }));
  }
);

Given("the issue {string} has labels {string}", async (issueId, labels) => {
  const issuePath = path.join(requireProjectRoot(), "issues", `${issueId}.json`);
  const issue = JSON.parse(await readFile(issuePath, "utf-8"));
  issue.labels = labels.split(",").map((label) => label.trim()).filter(Boolean);
  await writeFile(issuePath, JSON.stringify(issue, null, 2));
});

When(
  "I set the routing assignment through the issue write API for {string} to {word} {string}",
  async function (issueId, kind, name) {
    this.issueWriteResponse = await assignmentRequest(issueId, { kind, name });
    this.issueWritePayload = await this.issueWriteResponse.json();
  }
);

When(
  "I clear the routing assignment through the issue write API for {string}",
  async function (issueId) {
    this.issueWriteResponse = await assignmentRequest(issueId, { clear: true });
    this.issueWritePayload = await this.issueWriteResponse.json();
  }
);

Then(
  "the issue write API response should be successful with labels {string}",
  async function (labels) {
    expect(this.issueWriteResponse.ok).toBe(true);
    expect([...this.issueWritePayload.issue.labels].sort()).toEqual(labels.split(",").sort());
  }
);

Then(
  "the issue write API response should show agent assignment {string} {string}",
  async function (kind, name) {
    const assignment = this.issueWritePayload.issue.custom?.agent_assignment;
    expect(assignment?.kind).toBe(kind);
    expect(assignment?.name).toBe(name);
  }
);

Then("the issue write API response should show no agent assignment", async function () {
  expect(this.issueWritePayload.issue.custom?.agent_assignment).toBeUndefined();
});
