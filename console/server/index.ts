import express from "express";
import cors from "cors";
import path from "path";
import fs from "fs/promises";
import yaml from "js-yaml";
import chokidar from "chokidar";
import type { Issue, IssuesSnapshot, ProjectConfig } from "../src/types/issues";
import { fileURLToPath } from "url";

const app = express();
const port = Number(process.env.CONSOLE_PORT ?? 5174);
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = process.env.CONSOLE_PROJECT_ROOT
  ? path.resolve(process.env.CONSOLE_PROJECT_ROOT)
  : path.resolve(__dirname, "..", "..", "project");
const issuesDir = path.join(projectRoot, "issues");
const configPath = path.join(projectRoot, "config.yaml");

app.use(
  cors({
    origin: "http://localhost:5173",
    methods: ["GET"]
  })
);

async function loadConfig(): Promise<ProjectConfig> {
  let raw: string;
  try {
    raw = await fs.readFile(configPath, "utf-8");
  } catch (error) {
    const err = error as NodeJS.ErrnoException;
    if (err.code === "ENOENT") {
      throw new Error("project/config.yaml not found");
    }
    throw error;
  }

  const parsed = yaml.load(raw);
  if (!parsed || typeof parsed !== "object") {
    throw new Error("config.yaml is invalid");
  }
  return parsed as ProjectConfig;
}

async function loadIssues(): Promise<Issue[]> {
  let entries: fs.Dirent[];
  try {
    entries = await fs.readdir(issuesDir, { withFileTypes: true });
  } catch (error) {
    const err = error as NodeJS.ErrnoException;
    if (err.code === "ENOENT") {
      throw new Error("project/issues directory not found");
    }
    throw error;
  }
  const issueFiles = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => path.join(issuesDir, entry.name));

  const issues = await Promise.all(
    issueFiles.map(async (file) => {
      const raw = await fs.readFile(file, "utf-8");
      return JSON.parse(raw) as Issue;
    })
  );

  return issues.sort((a, b) => a.id.localeCompare(b.id));
}

async function buildSnapshot(): Promise<IssuesSnapshot> {
  const [config, issues] = await Promise.all([loadConfig(), loadIssues()]);
  return {
    config,
    issues,
    updated_at: new Date().toISOString()
  };
}

app.get("/api/config", async (_req, res) => {
  try {
    const config = await loadConfig();
    res.json(config);
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

app.get("/api/issues", async (_req, res) => {
  try {
    const issues = await loadIssues();
    res.json(issues);
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

app.get("/api/issues/:id", async (req, res) => {
  try {
    const issues = await loadIssues();
    const issue = issues.find((item) => item.id === req.params.id);
    if (!issue) {
      res.status(404).json({ error: "issue not found" });
      return;
    }
    res.json(issue);
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

const sseClients = new Set<express.Response>();

app.get("/api/events", async (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();
  res.write("retry: 1000\n\n");

  sseClients.add(res);

  try {
    const snapshot = await buildSnapshot();
    res.write(`data: ${JSON.stringify(snapshot)}\n\n`);
  } catch (error) {
    res.write(
      `data: ${JSON.stringify({
        error: (error as Error).message,
        updated_at: new Date().toISOString()
      })}\n\n`
    );
  }

  req.on("close", () => {
    sseClients.delete(res);
  });
});

function broadcastSnapshot(snapshot: IssuesSnapshot) {
  const payload = `data: ${JSON.stringify(snapshot)}\n\n`;
  for (const client of sseClients) {
    client.write(payload);
  }
}

let debounceTimer: NodeJS.Timeout | null = null;

const watcher = chokidar.watch(projectRoot, {
  ignoreInitial: true,
  awaitWriteFinish: {
    stabilityThreshold: 200,
    pollInterval: 100
  }
});

watcher.on("all", () => {
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(async () => {
    debounceTimer = null;
    try {
      const snapshot = await buildSnapshot();
      broadcastSnapshot(snapshot);
    } catch (error) {
      const payload = {
        error: (error as Error).message,
        updated_at: new Date().toISOString()
      };
      const message = `data: ${JSON.stringify(payload)}\n\n`;
      for (const client of sseClients) {
        client.write(message);
      }
    }
  }, 250);
});

app.listen(port, () => {
  console.log(`Taskulus console server running on ${port}`);
});
