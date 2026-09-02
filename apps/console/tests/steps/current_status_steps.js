import { Given, When, Then } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { mkdir, readFile, readdir, writeFile } from "fs/promises";
import path from "path";
import yaml from "js-yaml";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;
const consoleConfigPath = process.env.CONSOLE_CONFIG_PATH
  ?? (projectRoot ? path.join(path.dirname(projectRoot), ".kanbus.yml") : null);
const consolePort = process.env.CONSOLE_PORT ?? "5174";
const consoleApiBase =
  process.env.CONSOLE_API_BASE ?? `http://localhost:${consolePort}/api`;

function requireProjectRoot() {
  if (!projectRoot) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for current status tests");
  }
  return projectRoot;
}

function statusIndex(world) {
  if (!world.statusIssueByTitle) {
    world.statusIssueByTitle = {};
  }
  return world.statusIssueByTitle;
}

function nextStatusId(world) {
  world.statusIssueSeq = (world.statusIssueSeq ?? 0) + 1;
  return `kanbus-status-${world.statusIssueSeq}`;
}

function markConsoleDirty(world) {
  world.metricsDirty = true;
  world.metricsStale = true;
}

function buildStatusIssue({
  id,
  title,
  type = "task",
  updatedAt,
  parent = null,
  rightNowSummary = null
}) {
  return {
    id,
    title,
    description: "",
    type,
    status: "open",
    priority: 2,
    assignee: null,
    creator: "fixture",
    parent,
    labels: [],
    dependencies: [],
    comments: [],
    created_at: updatedAt,
    updated_at: updatedAt,
    closed_at: null,
    right_now_summary: rightNowSummary,
    right_now_updated_at: rightNowSummary ? updatedAt : null,
    custom: {}
  };
}

async function writeStatusIssue(issue) {
  const issueDir = path.join(requireProjectRoot(), "issues");
  await mkdir(issueDir, { recursive: true });
  await writeFile(
    path.join(issueDir, `${issue.id}.json`),
    JSON.stringify(issue, null, 2)
  );
}

async function loadIssueByTitle(title) {
  const issueDir = path.join(requireProjectRoot(), "issues");
  const entries = await readdir(issueDir);
  for (const entry of entries) {
    if (!entry.endsWith(".json")) {
      continue;
    }
    const payload = JSON.parse(await readFile(path.join(issueDir, entry), "utf-8"));
    if (payload.title === title) {
      return payload;
    }
  }
  return null;
}

async function loadKanbusConfigFile() {
  if (!consoleConfigPath) {
    return {};
  }
  try {
    const contents = await readFile(consoleConfigPath, "utf-8");
    return yaml.load(contents) ?? {};
  } catch {
    return {};
  }
}

async function saveKanbusConfigFile(config) {
  if (!consoleConfigPath) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for config access");
  }
  const contents = yaml.dump(config, { sortKeys: false });
  await writeFile(consoleConfigPath, contents, "utf-8");
}

async function refreshIssuesSnapshot() {
  const response = await fetch(`${consoleApiBase}/issues?refresh=1`);
  if (!response.ok) {
    throw new Error(`console issues request failed: ${response.status}`);
  }
  return response.json();
}

async function waitForIssueField(issueId, predicate, timeoutMs = 8000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const issues = await refreshIssuesSnapshot();
    const issue = issues.find((entry) => entry.id === issueId);
    if (issue && predicate(issue)) {
      return issue;
    }
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  throw new Error(`Timed out waiting for issue update: ${issueId}`);
}

function feedRow(page, title) {
  return page.locator(`[data-testid="status-feed-row"][data-issue-title="${title}"]`);
}

function treeRow(page, title) {
  return page.locator(`[data-testid="status-tree-row"][data-issue-title="${title}"]`);
}

Then("the current status view should be active", async function () {
  await expect(this.page.getByTestId("view-toggle-now")).toHaveAttribute(
    "data-active",
    "true"
  );
  await expect(this.page.getByTestId("current-status-view")).toBeVisible();
});

Given(
  "a status issue {string} updated at {string}",
  async function (title, timestamp) {
    markConsoleDirty(this);
    const id = nextStatusId(this);
    statusIndex(this)[title] = id;
    await writeStatusIssue(
      buildStatusIssue({ id, title, updatedAt: timestamp })
    );
  }
);

Given(
  "a status hierarchy root {string} of type {string} updated at {string}",
  async function (title, issueType, timestamp) {
    markConsoleDirty(this);
    const id = nextStatusId(this);
    statusIndex(this)[title] = id;
    await writeStatusIssue(
      buildStatusIssue({
        id,
        title,
        type: issueType,
        updatedAt: timestamp
      })
    );
  }
);

Given(
  "a status hierarchy child {string} of type {string} under {string} updated at {string}",
  async function (title, issueType, parentTitle, timestamp) {
    markConsoleDirty(this);
    const parentId = statusIndex(this)[parentTitle];
    if (!parentId) {
      throw new Error(`parent status issue not found: ${parentTitle}`);
    }
    const id = nextStatusId(this);
    statusIndex(this)[title] = id;
    await writeStatusIssue(
      buildStatusIssue({
        id,
        title,
        type: issueType,
        updatedAt: timestamp,
        parent: parentId
      })
    );
  }
);

Given(
  "the console right now configuration has default_tree_expanded {word}",
  async function (expected) {
    markConsoleDirty(this);
    const config = await loadKanbusConfigFile();
    config.right_now = {
      ...(config.right_now ?? {}),
      default_tree_expanded: expected.toLowerCase() === "true"
    };
    await saveKanbusConfigFile(config);
    await refreshIssuesSnapshot();
  }
);

Given(
  "the status issue {string} has right-now summary {string}",
  async function (title, summary) {
    markConsoleDirty(this);
    const issue = await loadIssueByTitle(title);
    if (!issue) {
      throw new Error(`issue not found: ${title}`);
    }
    issue.right_now_summary = summary;
    issue.right_now_updated_at = issue.updated_at ?? issue.created_at;
    statusIndex(this)[title] = issue.id;
    await writeStatusIssue(issue);
  }
);

Given(
  "the console issue {string} has right-now summary {string}",
  async function (title, summary) {
    markConsoleDirty(this);
    const issue = await loadIssueByTitle(title);
    if (!issue) {
      throw new Error(`issue not found: ${title}`);
    }
    issue.right_now_summary = summary;
    issue.right_now_updated_at = issue.updated_at ?? issue.created_at;
    await writeStatusIssue(issue);
    await waitForIssueField(
      issue.id,
      (entry) => entry.right_now_summary === summary
    );
  }
);

Given("35 status issues exist with sequential update times", async function () {
  markConsoleDirty(this);
  for (let index = 0; index < 35; index += 1) {
    const title = `Status issue ${index + 1}`;
    const id = nextStatusId(this);
    statusIndex(this)[title] = id;
    const updatedAt = new Date(Date.UTC(2026, 0, 1, 10, 0, 0));
    updatedAt.setUTCDate(updatedAt.getUTCDate() + index);
    await writeStatusIssue(
      buildStatusIssue({
        id,
        title,
        updatedAt: updatedAt.toISOString()
      })
    );
  }
});

When("I enable the status tree view", async function () {
  await this.page.getByTestId("status-tree-toggle").check();
  await expect(this.page.getByTestId("status-tree")).toBeVisible();
});

When("I disable the status tree view", async function () {
  await this.page.getByTestId("status-tree-toggle").uncheck();
  await expect(this.page.getByTestId("status-feed")).toBeVisible();
});

When("I collapse the status tree node for {string}", async function (title) {
  await treeRow(this.page, title).getByTestId("status-tree-node-toggle").click();
});

When("I expand the status tree node for {string}", async function (title) {
  await treeRow(this.page, title).getByTestId("status-tree-node-toggle").click();
});

When(
  "the right-now summary for {string} is updated to {string}",
  async function (title, summary) {
    const issue = await loadIssueByTitle(title);
    if (!issue) {
      throw new Error(`issue not found: ${title}`);
    }
    issue.right_now_summary = summary;
    issue.right_now_updated_at = issue.updated_at ?? issue.created_at;
    await writeStatusIssue(issue);
    await waitForIssueField(
      issue.id,
      (entry) => entry.right_now_summary === summary
    );
    await expect
      .poll(async () => feedRow(this.page, title).getByTestId("status-feed-summary").textContent(), {
        timeout: 8000
      })
      .toBe(summary);
  }
);

When(
  "the console receives an issue update for {string} with right-now summary {string}",
  async function (title, summary) {
    const issue = await loadIssueByTitle(title);
    if (!issue) {
      throw new Error(`issue not found: ${title}`);
    }
    issue.right_now_summary = summary;
    issue.right_now_updated_at = issue.updated_at ?? issue.created_at;
    await writeStatusIssue(issue);
    await expect
      .poll(async () => feedRow(this.page, title).getByTestId("status-feed-summary").textContent(), {
        timeout: 8000
      })
      .toBe(summary);
  }
);

Then(
  "the status feed should list issues in order {string}",
  async function (order) {
    const expected = order.split(",").map((title) => title.trim());
    await expect
      .poll(
        async () =>
          (
            await this.page
              .locator('[data-testid="status-feed-row"] [data-testid="status-feed-title"]')
              .allTextContents()
          ).map((title) => title.trim()),
        { timeout: 8000 }
      )
      .toEqual(expected);
  }
);

Then(
  "the status tree should list issues in order {string}",
  async function (order) {
    const expected = order.split(",").map((title) => title.trim());
    await expect
      .poll(
        async () =>
          (
            await this.page
              .locator('[data-testid="status-tree-row"] [data-testid="status-tree-title"]')
              .allTextContents()
          ).map((title) => title.trim()),
        { timeout: 8000 }
      )
      .toEqual(expected);
  }
);

Then(
  "the status tree node for {string} should be expanded",
  async function (title) {
    await expect(treeRow(this.page, title)).toHaveAttribute(
      "data-tree-expanded",
      "true"
    );
  }
);

Then(
  "the status tree node for {string} should be collapsed",
  async function (title) {
    await expect(treeRow(this.page, title)).toHaveAttribute(
      "data-tree-expanded",
      "false"
    );
  }
);

Then(
  "the status feed row for {string} should show title {string}",
  async function (title, expected) {
    await expect(feedRow(this.page, title).getByTestId("status-feed-title")).toHaveText(
      expected
    );
  }
);

Then(
  "the status tree row for {string} should show title {string}",
  async function (title, expected) {
    await expect(treeRow(this.page, title).getByTestId("status-tree-title")).toHaveText(
      expected
    );
  }
);

Then(
  "the status feed row for {string} should show right-now summary {string}",
  async function (title, expected) {
    await expect(
      feedRow(this.page, title).getByTestId("status-feed-summary")
    ).toHaveText(expected);
  }
);

Then(
  "the status tree row for {string} should show right-now summary {string}",
  async function (title, expected) {
    await expect(
      treeRow(this.page, title).getByTestId("status-tree-summary")
    ).toHaveText(expected);
  }
);

Then("the status feed should contain {int} rows", async function (count) {
  await expect(this.page.getByTestId("status-feed-row")).toHaveCount(count);
});

Then(
  "the issue detail should show right-now summary {string}",
  async function (summary) {
    await expect(this.page.getByTestId("issue-right-now-summary")).toHaveText(
      summary
    );
  }
);
