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
  // Reset console state to a clean baseline (server running, no focus/view/search)
  const statePath = path.join(root, "..", ".cache", "console_state.json");
  const baselineState = {
    server_running: true,
    focused_issue_id: undefined,
    focused_comment_id: null,
    view_mode: "issues",
    search_query: ""
  };
  await fs.writeFile(statePath, JSON.stringify(baselineState, null, 2), "utf-8");
});

Given("an issue {string} exists with title {string}", async function (id, title) {
  const root = projectRoot();
  const { projectDir } = await ensureProjectSkeleton(root);
  await writeIssue(projectDir, id, title);
});

Given("the console server is running", async function () {
  const root = projectRoot();
  const { cacheDir } = await ensureProjectSkeleton(root);
  const statePath = path.join(cacheDir, "console_state.json");
  let state = {};
  try {
    state = JSON.parse(await fs.readFile(statePath, "utf-8"));
  } catch (err) {
    if (!err || err.code !== "ENOENT") throw err;
  }
  state.server_running = true;
  await fs.mkdir(path.dirname(statePath), { recursive: true });
  await fs.writeFile(statePath, JSON.stringify(state, null, 2), "utf-8");
});

Given("the console server is not running", async function () {
  const root = projectRoot();
  const { cacheDir } = await ensureProjectSkeleton(root);
  const statePath = path.join(cacheDir, "console_state.json");
  let state = {};
  try {
    state = JSON.parse(await fs.readFile(statePath, "utf-8"));
  } catch (err) {
    if (!err || err.code !== "ENOENT") throw err;
  }
  state.server_running = false;
  await fs.mkdir(path.dirname(statePath), { recursive: true });
  await fs.writeFile(statePath, JSON.stringify(state, null, 2), "utf-8");
});

Given("no issue is focused in the console", async function () {
  const root = projectRoot();
  const { cacheDir } = await ensureProjectSkeleton(root);
  const statePath = path.join(cacheDir, "console_state.json");
  let state = {};
  try {
    state = JSON.parse(await fs.readFile(statePath, "utf-8"));
  } catch (err) {
    if (!err || err.code !== "ENOENT") throw err;
  }
  state.focused_issue_id = undefined;
  await fs.mkdir(path.dirname(statePath), { recursive: true });
  await fs.writeFile(statePath, JSON.stringify(state, null, 2), "utf-8");
});

Given("the console focused issue is {string}", async function (id) {
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

Given("the console view mode is {string}", async function (mode) {
  const root = projectRoot();
  const { cacheDir } = await ensureProjectSkeleton(root);
  const statePath = path.join(cacheDir, "console_state.json");
  let state = {};
  try {
    state = JSON.parse(await fs.readFile(statePath, "utf-8"));
  } catch (err) {
    if (!err || err.code !== "ENOENT") throw err;
  }
  state.view_mode = mode;
  await fs.mkdir(path.dirname(statePath), { recursive: true });
  await fs.writeFile(statePath, JSON.stringify(state, null, 2), "utf-8");
});

Given("the console search query is {string}", async function (query) {
  const root = projectRoot();
  const { cacheDir } = await ensureProjectSkeleton(root);
  const statePath = path.join(cacheDir, "console_state.json");
  let state = {};
  try {
    state = JSON.parse(await fs.readFile(statePath, "utf-8"));
  } catch (err) {
    if (!err || err.code !== "ENOENT") throw err;
  }
  state.search_query = query;
  await fs.mkdir(path.dirname(statePath), { recursive: true });
  await fs.writeFile(statePath, JSON.stringify(state, null, 2), "utf-8");
});
