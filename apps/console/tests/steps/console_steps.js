import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { readFile, readdir, writeFile } from "fs/promises";
import path from "path";
import yaml from "js-yaml";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;
const projectIssuesRoot = projectRoot ? path.join(projectRoot, "issues") : null;
const consolePort = process.env.CONSOLE_PORT ?? "5174";
const consoleBaseUrl =
  process.env.CONSOLE_BASE_URL ?? `http://localhost:${consolePort}/`;
const consoleApiBase =
  process.env.CONSOLE_API_BASE ?? `${consoleBaseUrl.replace(/\/+$/, "")}/api`;

function issueCardLocator(page, title) {
  return page.locator(".issue-card", { hasText: title });
}

async function loadIssues() {
  if (!projectIssuesRoot) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for issue file access");
  }
  const entries = await readdir(projectIssuesRoot);
  const issues = [];
  for (const entry of entries) {
    if (!entry.endsWith(".json")) {
      continue;
    }
    const payload = await readFile(path.join(projectIssuesRoot, entry), "utf-8");
    issues.push(JSON.parse(payload));
  }
  return issues;
}

async function writeIssue(issue) {
  if (!projectIssuesRoot) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for issue file access");
  }
  const filePath = path.join(projectIssuesRoot, `${issue.id}.json`);
  await writeFile(filePath, JSON.stringify(issue, null, 2));
}

async function fetchIssuesFromServer() {
  const response = await fetch(`${consoleApiBase}/issues?refresh=1`);
  if (!response.ok) {
    throw new Error(`console issues request failed: ${response.status}`);
  }
  return response.json();
}

async function waitForIssueUpdate(issueId, predicate) {
  const start = Date.now();
  while (Date.now() - start < 5000) {
    const issues = await fetchIssuesFromServer();
    const issue = issues.find((entry) => entry.id === issueId);
    if (issue && predicate(issue)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for issue update: ${issueId}`);
}

function normalizeTimestamp(value) {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toISOString();
}

Given("the console is open", async function () {
  await expect(this.page.getByTestId("open-settings")).toBeVisible();
});

When(
  "I view an issue card or detail that shows priority",
  async function () {
    const priorityLocator = this.page.locator(".issue-accent-priority").first();
    await expect(priorityLocator).toBeVisible();
    this.priorityElement = priorityLocator;
  }
);

Then(
  "the priority label should use the priority color as background",
  async function () {
    if (!this.priorityElement) {
      throw new Error("priority element was not found in the previous step");
    }
    const backgroundColor = await this.priorityElement.evaluate((element) => {
      const style = window.getComputedStyle(element);
      return style.backgroundColor;
    });
    expect(backgroundColor).toBeTruthy();
    expect(backgroundColor).not.toBe("rgba(0, 0, 0, 0)");
  }
);

Then(
  "the priority label text should use the normal text foreground color",
  async function () {
    if (!this.priorityElement) {
      throw new Error("priority element was not found in the previous step");
    }
    const { color, backgroundColor } = await this.priorityElement.evaluate(
      (element) => {
        const style = window.getComputedStyle(element);
        return {
          color: style.color,
          backgroundColor: style.backgroundColor
        };
      }
    );
    expect(color).toBeTruthy();
    expect(color).not.toBe(backgroundColor);
  }
);

Given("local storage is cleared", async function () {
  await this.page.evaluate(() => window.localStorage.clear());
});

When("the console is reloaded", async function () {
  await this.page.reload({ waitUntil: "domcontentloaded" });
});

When("I open the console route {string}", async function (routePath) {
  const target = routePath.startsWith("http")
    ? routePath
    : `${consoleBaseUrl.replace(/\/+$/, "")}/${routePath.replace(/^\/+/, "")}`;
  await this.page.goto(target, { waitUntil: "domcontentloaded" });
});

When("I switch to the {string} tab", async function (tabName) {
  const resolved = tabName === "Tasks" ? "Issues" : tabName;
  await this.page.getByRole("tab", { name: resolved }).click();
});

When("I open the task {string}", async function (title) {
  await issueCardLocator(this.page, title).click();
});

When("a new task issue named {string} is added", async function (title) {
  if (!projectRoot) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for SSE tests");
  }
  const issueId = "kanbus-task-2";
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
    comments: [],
    created_at: "2026-02-11T04:00:00.000Z",
    updated_at: "2026-02-11T04:00:00.000Z",
    closed_at: null,
    custom: {}
  };
  const filePath = path.join(projectRoot, "issues", `${issueId}.json`);
  await writeFile(filePath, JSON.stringify(issue, null, 2));
});

Given(
  "the console configuration sets time zone {string}",
  async function (timeZone) {
    if (!projectRoot) {
      throw new Error("CONSOLE_PROJECT_ROOT is required for SSE tests");
    }
    const repoRoot = path.dirname(projectRoot);
    const overridePath = path.join(repoRoot, ".kanbus.override.yml");
    const contents = yaml.dump({ time_zone: timeZone }, { sortKeys: false });
    await writeFile(overridePath, contents);
    this.overridePath = overridePath;
  }
);

Given(
  "the console has a comment from {string} at {string} on task {string}",
  async function (author, timestamp, title) {
    const issues = await loadIssues();
    const issue = issues.find((entry) => entry.title === title);
    if (!issue) {
      throw new Error(`Issue not found: ${title}`);
    }
    const comments = Array.isArray(issue.comments) ? issue.comments : [];
    comments.push({
      author,
      text: "Test comment",
      created_at: timestamp
    });
    issue.comments = comments;
    await writeIssue(issue);
    await waitForIssueUpdate(issue.id, (entry) =>
      Array.isArray(entry.comments)
      && entry.comments.some(
        (comment) =>
          comment.author === author
          && normalizeTimestamp(comment.created_at)
            === normalizeTimestamp(timestamp)
      )
    );
  }
);

Given(
  "the console has a task {string} created at {string} updated at {string}",
  async function (title, createdAt, updatedAt) {
    const issues = await loadIssues();
    const issue = issues.find((entry) => entry.title === title);
    if (!issue) {
      throw new Error(`Issue not found: ${title}`);
    }
    issue.created_at = createdAt;
    issue.updated_at = updatedAt;
    await writeIssue(issue);
    await waitForIssueUpdate(
      issue.id,
      (entry) =>
        normalizeTimestamp(entry.created_at)
          === normalizeTimestamp(createdAt)
        && normalizeTimestamp(entry.updated_at)
          === normalizeTimestamp(updatedAt)
    );
  }
);

Given(
  "the console has a closed task {string} created at {string} updated at {string} closed at {string}",
  async function (title, createdAt, updatedAt, closedAt) {
    const issues = await loadIssues();
    const issue = issues.find((entry) => entry.title === title);
    if (!issue) {
      throw new Error(`Issue not found: ${title}`);
    }
    issue.created_at = createdAt;
    issue.updated_at = updatedAt;
    issue.closed_at = closedAt;
    await writeIssue(issue);
    await waitForIssueUpdate(
      issue.id,
      (entry) =>
        normalizeTimestamp(entry.created_at)
          === normalizeTimestamp(createdAt)
        && normalizeTimestamp(entry.updated_at)
          === normalizeTimestamp(updatedAt)
        && normalizeTimestamp(entry.closed_at)
          === normalizeTimestamp(closedAt)
    );
  }
);

Given(
  "the console has an assignee {string} on task {string}",
  async function (assignee, title) {
    const issues = await loadIssues();
    const issue = issues.find((entry) => entry.title === title);
    if (!issue) {
      throw new Error(`Issue not found: ${title}`);
    }
    issue.assignee = assignee;
    await writeIssue(issue);
    await waitForIssueUpdate(issue.id, (entry) => entry.assignee === assignee);
  }
);

Then("I should see the issue {string}", async function (title) {
  await expect(issueCardLocator(this.page, title)).toBeVisible();
});

Then("I should not see the issue {string}", async function (title) {
  await expect(issueCardLocator(this.page, title)).toHaveCount(0);
});

Then("the {string} tab should be selected", async function (tabName) {
  const resolved = tabName === "Tasks" ? "Issues" : tabName;
  await expect(this.page.getByRole("tab", { name: resolved })).toHaveAttribute(
    "aria-selected",
    "true"
  );
});

Then("no view tab should be selected", async function () {
  const selectedTabs = this.page.locator(
    '[data-selector="view"][role="tab"][aria-selected="true"]'
  );
  await expect(selectedTabs).toHaveCount(0);
});

Then("the detail panel should show issue {string}", async function (title) {
  await expect(this.page.locator(".detail-card", { hasText: title })).toBeVisible();
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
  const stored = await this.page.evaluate(() => window.localStorage.getItem("kanbus.console.appearance"));
  expect(stored).not.toBeNull();
  const parsed = JSON.parse(stored);
  expect(parsed.theme).toBe(theme);
});

Then("the mode should be {string}", async function (mode) {
  const stored = await this.page.evaluate(() => window.localStorage.getItem("kanbus.console.appearance"));
  expect(stored).not.toBeNull();
  const parsed = JSON.parse(stored);
  expect(parsed.mode).toBe(mode);
});

Then("the typeface should be {string}", async function (font) {
  const stored = await this.page.evaluate(() => window.localStorage.getItem("kanbus.console.appearance"));
  expect(stored).not.toBeNull();
  const parsed = JSON.parse(stored);
  expect(parsed.font).toBe(font);
});

Then("the motion mode should be {string}", async function (motion) {
  const stored = await this.page.evaluate(() => window.localStorage.getItem("kanbus.console.appearance"));
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

Then("the comment timestamp should be {string}", async function (timestamp) {
  const commentTimestamp = this.page
    .locator(".detail-comment")
    .first()
    .locator(".text-xs.text-muted")
    .first();
  await expect(commentTimestamp).toHaveText(timestamp);
});

Then(
  "the issue metadata should include created timestamp {string}",
  async function (timestamp) {
    await expect(this.page.locator('[data-testid="issue-created-at"]')).toHaveText(
      timestamp
    );
  }
);

Then(
  "the issue metadata should include updated timestamp {string}",
  async function (timestamp) {
    await expect(this.page.locator('[data-testid="issue-updated-at"]')).toHaveText(
      timestamp
    );
  }
);

Then(
  "the issue metadata should include closed timestamp {string}",
  async function (timestamp) {
    await expect(this.page.locator('[data-testid="issue-closed-at"]')).toHaveText(
      timestamp
    );
  }
);

Then("the issue metadata should include assignee {string}", async function (assignee) {
  await expect(this.page.locator('[data-testid="issue-assignee"]')).toHaveText(
    assignee
  );
});
