import { Given } from "@cucumber/cucumber";
import { promises as fs } from "fs";
import path from "path";

function projectRoot() {
  const root = process.env.CONSOLE_PROJECT_ROOT;
  if (!root) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for console steps");
  }
  return path.resolve(root);
}

async function ensureProjectSkeleton(root) {
  const projectDir = path.join(root, "issues");
  await fs.mkdir(projectDir, { recursive: true });
  const cacheDir = path.join(root, "..", ".cache");
  await fs.mkdir(cacheDir, { recursive: true });
  return { projectDir, cacheDir };
}

async function writeIssue(projectDir, id, title) {
  const now = new Date().toISOString();
  const issue = {
    id,
    title,
    description: "",
    type: "task",
    status: "open",
    priority: 2,
    assignee: null,
    creator: "fixture",
    labels: [],
    dependencies: [],
    comments: [],
    created_at: now,
    updated_at: now,
    closed_at: null,
    custom: {}
  };
  const file = path.join(projectDir, `${id}.json`);
  await fs.writeFile(file, JSON.stringify(issue, null, 2), "utf-8");
}

Given("a Kanbus project with default configuration", async function () {
  const root = projectRoot();
  const { projectDir } = await ensureProjectSkeleton(root);
  const configPath = path.join(root, "..", ".kanbus.yml");
  const config = [
    "project_directory: project",
    "project_key: kanbus",
    "beads_compatibility: false"
  ].join("\n");
  await fs.writeFile(configPath, config, "utf-8");
  // Ensure issues dir exists
  await fs.mkdir(projectDir, { recursive: true });
});

Given('an issue "{word}" exists with title "{string}"', async function (id, title) {
  const root = projectRoot();
  const { projectDir } = await ensureProjectSkeleton(root);
  await writeIssue(projectDir, id, title);
});

Given("the console server is running", async function () {
  // The dev server is started by the test harness (start-server-and-test).
  // Nothing to do here; this step exists for clarity.
});

Given('the console focused issue is "{word}"', async function (id) {
  const root = projectRoot();
  const { cacheDir } = await ensureProjectSkeleton(root);
  const statePath = path.join(cacheDir, "console_state.json");
  const state = {
    focused_issue_id: id,
    focused_comment_id: null,
    view_mode: "issues",
    search_query: null
  };
  await fs.writeFile(statePath, JSON.stringify(state, null, 2), "utf-8");
});
