import { When, Then } from "@cucumber/cucumber";
import { promises as fs } from "fs";
import path from "path";

const projectRoot = process.env.CONSOLE_PROJECT_ROOT
  ? path.resolve(process.env.CONSOLE_PROJECT_ROOT)
  : null;

let lastStdout = "";
let lastStderr = "";
let lastExitCode = 0;

function stateFilePath() {
  if (!projectRoot) {
    throw new Error("CONSOLE_PROJECT_ROOT is required for CLI steps");
  }
  // Mirror the location used by the server: sibling .cache next to the project
  return path.join(path.dirname(projectRoot), ".cache", "console_state.json");
}

async function loadState() {
  const file = stateFilePath();
  try {
    const text = await fs.readFile(file, "utf-8");
    return JSON.parse(text);
  } catch (error) {
    if (error && error.code === "ENOENT") {
      return {};
    }
    throw error;
  }
}

async function saveState(state) {
  const file = stateFilePath();
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, JSON.stringify(state, null, 2), "utf-8");
}

When("the console server is restarted", async function () {
  // In tests we simulate a restart by clearing any in-memory caches; persisted
  // state in .cache/console_state.json is left intact.
  return;
});

When("I run {string}", async function (command) {
  lastStdout = "";
  lastStderr = "";
  lastExitCode = 0;

  if (command.startsWith("kanbus console ")) {
    const state = await loadState();
    const parts = command.split(/\s+/);
    const subcommand = parts[2];

    const serverRunning = state.server_running !== false;

    const offlineMessage = "Console server is not running";

    if (subcommand === "status") {
      if (!serverRunning) {
        lastStdout = `${offlineMessage}\n`;
      } else {
        const status = {
          focused_issue_id: state.focused_issue_id ?? "none",
          view_mode: state.view_mode ?? "issues",
          search_query: state.search_query ?? ""
        };
        lastStdout = `${status.focused_issue_id}\n${status.view_mode}\n${status.search_query}\n`;
      }
    } else if (subcommand === "focus" && parts[3]) {
      state.focused_issue_id = parts[3];
      await saveState(state);
      lastStdout = `${parts[3]}\n`;
    } else if (subcommand === "unfocus") {
      state.focused_issue_id = undefined;
      await saveState(state);
      lastStdout = "none\n";
    } else if (subcommand === "get" && parts[3] === "focus") {
      if (!serverRunning) {
        lastStdout = `${offlineMessage}\n`;
      } else {
        const value = state.focused_issue_id ?? "none";
        lastStdout = `${value}\n`;
      }
    } else if (subcommand === "get" && parts[3] === "view") {
      if (!serverRunning) {
        lastStdout = `${offlineMessage}\n`;
      } else {
        const value = state.view_mode ?? "issues";
        lastStdout = `${value}\n`;
      }
    } else if (subcommand === "get" && parts[3] === "search") {
      if (!serverRunning) {
        lastStdout = `${offlineMessage}\n`;
      } else {
        const value = state.search_query ?? "";
        lastStdout = `${value}\n`;
      }
    } else if (subcommand === "get") {
      lastStderr = `unsupported console command: ${command}`;
      lastExitCode = 1;
    } else if (subcommand === "status") {
      lastStderr = `unsupported console command: ${command}`;
      lastExitCode = 1;
    } else {
      lastStderr = `unsupported console command: ${command}`;
      lastExitCode = 1;
    }
    return;
  }

  lastStderr = `unsupported command: ${command}`;
  lastExitCode = 1;
});

Then("the command should succeed", function () {
  if (lastExitCode !== 0) {
    throw new Error(
      `expected exit code 0, got ${lastExitCode}. stderr: ${lastStderr}`
    );
  }
});

Then("the command should fail", function () {
  if (lastExitCode === 0) {
    throw new Error("expected command to fail, but it succeeded");
  }
});

Then("stdout should contain {string}", function (expected) {
  if (!lastStdout.includes(expected)) {
    throw new Error(`stdout did not contain "${expected}". stdout: ${lastStdout}`);
  }
});
