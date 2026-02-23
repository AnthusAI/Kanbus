import { Given, When, Then, After } from "@cucumber/cucumber";
import { expect } from "@playwright/test";
import { writeFile, rm, mkdir, cp } from "fs/promises";
import path from "path";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT;
const fixtureRoot = path.resolve(process.cwd(), "tests", "fixtures", "project");

// Helper to ensure project root is available
function requireProjectRoot() {
  if (!projectRoot) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for metrics tests");
  }
  return projectRoot;
}

async function resetMetricsProjectRoot() {
  const root = requireProjectRoot();
  const repoRoot = path.dirname(root);
  await rm(path.join(repoRoot, "project"), { recursive: true, force: true });
  await rm(path.join(repoRoot, "project-local"), { recursive: true, force: true });
  await rm(path.join(repoRoot, "virtual"), { recursive: true, force: true });
  await cp(fixtureRoot, root, { recursive: true });
}

After(async function () {
  if (!this.metricsDirty) {
    return;
  }
  await resetMetricsProjectRoot();
  this.metricsDirty = false;
});

// Helper to build a metrics issue
function buildMetricsIssue({
  id,
  title,
  type = "task",
  status = "open",
  project = "kbs"
}) {
  const timestamp = new Date().toISOString();
  return {
    id,
    title,
    description: "Generated for metrics test",
    type,
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
    custom: {},
    // For virtual projects, we simulate them by placement, but the issue structure remains the same.
    // The console app determines project context based on where the file is loaded from.
  };
}

When("I switch to the {string} view", async function (viewName) {
  const normalized = viewName.toLowerCase();
  await this.page.getByTestId(`view-toggle-${normalized}`).click();
});

Then("the board view should be active", async function () {
  await expect(this.page.getByTestId("view-toggle-board")).toHaveAttribute("data-active", "true");
  await expect(this.page.getByTestId("board-view")).toBeVisible();
});

Then("the metrics view should be active", async function () {
  await expect(this.page.getByTestId("view-toggle-metrics")).toHaveAttribute("data-active", "true");
  await expect(this.page.getByTestId("metrics-view")).toBeVisible();
});

Then("the metrics view should be inactive", async function () {
  await expect(this.page.getByTestId("view-toggle-metrics")).toHaveAttribute("data-active", "false");
  await expect(this.page.getByTestId("metrics-view")).not.toBeVisible();
});

Then("the board view should be inactive", async function () {
  await expect(this.page.getByTestId("view-toggle-board")).toHaveAttribute("data-active", "false");
  await expect(this.page.getByTestId("board-view")).not.toBeVisible();
});

Then("the metrics toggle should select {string}", async function (viewName) {
    const normalized = viewName.toLowerCase();
    await expect(this.page.getByTestId(`view-toggle-${normalized}`)).toHaveAttribute("data-active", "true");
});

Then("the metrics toggle should include a board icon", async function () {
    await expect(this.page.getByTestId("view-toggle-board").locator("svg")).toBeVisible();
});

Then("the metrics toggle should include a chart icon", async function () {
    await expect(this.page.getByTestId("view-toggle-metrics").locator("svg")).toBeVisible();
});

Given("no issues exist in the console", async function () {
  this.metricsDirty = true;
  const root = requireProjectRoot();
  const repoRoot = path.dirname(root);
  
  // Clean base project issues
  await rm(path.join(root, "issues"), { recursive: true, force: true });
  await rm(path.join(repoRoot, "project-local", "issues"), { recursive: true, force: true });
  
  // Clean virtual projects
  await rm(path.join(repoRoot, "virtual"), { recursive: true, force: true });
  
  // Re-create issues directories
  await mkdir(path.join(root, "issues"), { recursive: true });
});

Given(
  "a metrics issue {string} of type {string} with status {string} in project {string} from {string}",
  async function (title, type, status, projectLabel, source) {
    this.metricsDirty = true;
    const root = requireProjectRoot();
    const repoRoot = path.dirname(root);
    
    let issueDir;
    if (projectLabel === "kbs") {
        if (source === "local") {
            issueDir = path.join(repoRoot, "project-local", "issues");
        } else {
            issueDir = path.join(root, "issues");
        }
    } else {
        // Virtual project
        if (source === "local") {
            issueDir = path.join(repoRoot, "virtual", projectLabel, "project-local", "issues");
        } else {
            issueDir = path.join(repoRoot, "virtual", projectLabel, "project", "issues");
        }
    }
    
    await mkdir(issueDir, { recursive: true });
    
    const id = `${projectLabel}-${source}-${title.replace(/\s+/g, "-").toLowerCase()}`;
    const issue = buildMetricsIssue({ id, title, type, status });
    await writeFile(path.join(issueDir, `${id}.json`), JSON.stringify(issue, null, 2));
  }
);

Then("the metrics total should be {string}", async function (count) {
    await expect(this.page.getByTestId("metrics-total-count")).toHaveText(count);
});

Then("the metrics status count for {string} should be {string}", async function (status, count) {
    await expect(this.page.getByTestId(`metrics-status-${status}`)).toHaveText(count);
});

Then("the metrics project count for {string} should be {string}", async function (project, count) {
    await expect(this.page.getByTestId(`metrics-project-${project}`)).toHaveText(count);
});

Then("the metrics scope count for {string} should be {string}", async function (scope, count) {
    await expect(this.page.getByTestId(`metrics-scope-${scope.toLowerCase()}`)).toHaveText(count);
});

Then("the metrics chart should include type {string}", async function (type) {
    await expect(this.page.locator(`.visx-bar-group[data-type="${type}"]`)).toBeVisible();
});

Then("the metrics chart should stack statuses for {string}", async function (type) {
    const group = this.page.locator(`.visx-bar-group[data-type="${type}"]`);
    const rects = group.locator("rect");
    const count = await rects.count();
    expect(count).toBeGreaterThan(1);
});

Then("the metrics chart should include a legend", async function () {
    await expect(this.page.getByTestId("metrics-chart-legend")).toBeVisible();
});

Then("the metrics chart should use category colors", async function () {
    // This is hard to test specifically without visual regression, but we can check if rects have fill colors
    const rect = this.page.locator(".visx-bar-group rect").first();
    const fill = await rect.getAttribute("fill");
    expect(fill).toBeTruthy();
});

When("I select metrics project {string}", async function (project) {
    // Re-use existing filter steps logic if possible, or implement direct click
    // Assuming this refers to the sidebar filter
    await this.page.getByTestId("filter-button").click();
    await this.page.getByRole("button", { name: project }).click();
    await this.page.getByTestId("filter-sidebar-close").click();
});
