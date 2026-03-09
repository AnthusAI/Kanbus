import express from "express";
import cors from "cors";
import path from "path";
import fs from "fs";
import { execFile } from "child_process";
import { promisify } from "util";
import chokidar from "chokidar";
import { resolvePortOrExit } from "../scripts/resolvePort";
import type { IssuesSnapshot } from "../src/types/issues";

const fsPromises = fs.promises;

const app = express();
const desiredPort = Number(process.env.CONSOLE_PORT ?? 5174);
const vitePort = Number(process.env.VITE_PORT ?? 5173);
// Default to wide bind for dev; override via VITE_HOST if needed
const viteHost = process.env.VITE_HOST ?? "0.0.0.0";
const allowedOrigins = new Set([
  `http://${viteHost}:${vitePort}`,
  `http://localhost:${vitePort}`,
  `http://127.0.0.1:${vitePort}`
]);
const projectRoot = process.env.CONSOLE_PROJECT_ROOT
  ? path.resolve(process.env.CONSOLE_PROJECT_ROOT)
  : null;
if (!projectRoot) {
  throw new Error("CONSOLE_PROJECT_ROOT is required");
}
const repoRoot = path.dirname(projectRoot);
const execFileAsync = promisify(execFile);
const kanbusPython = process.env.KANBUS_PYTHON ?? null;
const kanbusPythonArgs = (process.env.KANBUS_PYTHON_ARGS ?? "")
  .split(/\s+/)
  .map((value) => value.trim())
  .filter(Boolean);
const pythonPath = process.env.KANBUS_PYTHONPATH
  ? path.resolve(repoRoot, process.env.KANBUS_PYTHONPATH)
  : null;
const consoleLogPath = process.env.CONSOLE_LOG_PATH
  ? path.resolve(process.env.CONSOLE_LOG_PATH)
  : path.join(repoRoot, "console.log");
const consoleLogStream = fs.createWriteStream(consoleLogPath, { flags: "a" });

consoleLogStream.on("error", (error) => {
  console.error("[console] telemetry log stream error", error);
});

function writeConsoleLog(entry: Record<string, unknown>): void {
  if (!consoleLogStream.writable) {
    return;
  }
  consoleLogStream.write(`${JSON.stringify(entry)}\n`);
}

function classifyContentType(rawType: unknown): "json" | "text" | "other" | "unknown" {
  if (typeof rawType !== "string") {
    return "unknown";
  }
  const normalized = rawType.toLowerCase();
  if (normalized.includes("application/json")) {
    return "json";
  }
  if (normalized.includes("text/plain")) {
    return "text";
  }
  return "other";
}

function classifyContentLength(rawLength: unknown): "empty" | "small" | "medium" | "large" | "unknown" {
  if (typeof rawLength !== "string") {
    return "unknown";
  }
  const parsed = Number.parseInt(rawLength, 10);
  if (!Number.isFinite(parsed) || parsed < 0) {
    return "unknown";
  }
  if (parsed === 0) {
    return "empty";
  }
  if (parsed <= 1024) {
    return "small";
  }
  if (parsed <= 65536) {
    return "medium";
  }
  return "large";
}

writeConsoleLog({
  type: "startup",
  at: new Date().toISOString(),
  logPath: consoleLogPath
});

app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin || allowedOrigins.has(origin)) {
        callback(null, true);
        return;
      }
      callback(null, false);
    },
    methods: ["GET", "POST", "PUT", "DELETE"]
  })
);

let cachedSnapshot: IssuesSnapshot | null = null;
let snapshotPromise: Promise<IssuesSnapshot> | null = null;

function logConsoleEvent(
  label: string,
  details?: Record<string, unknown>
): void {
  const payload = {
    at: new Date().toISOString(),
    ...details
  };
  console.log(`[console] ${label}`, payload);
  writeConsoleLog({ type: "event", label, payload });
}

async function runSnapshot(): Promise<IssuesSnapshot> {
  const command = kanbusPython ?? "kanbus";
  const args = kanbusPython
    ? [...kanbusPythonArgs, "-m", "kanbus.cli", "console", "snapshot"]
    : ["console", "snapshot"];
  const { stdout } = await execFileAsync(command, args, {
    cwd: repoRoot,
    env: {
      ...process.env,
      KANBUS_NO_DAEMON: "1",
      PYTHONPATH: kanbusPython ? pythonPath ?? process.env.PYTHONPATH : process.env.PYTHONPATH
    },
    maxBuffer: 10 * 1024 * 1024
  });
  return JSON.parse(stdout) as IssuesSnapshot;
}

async function getSnapshot(): Promise<IssuesSnapshot> {
  if (cachedSnapshot) {
    return cachedSnapshot;
  }
  if (!snapshotPromise) {
    snapshotPromise = runSnapshot()
      .then((snapshot) => {
        cachedSnapshot = snapshot;
        return snapshot;
      })
      .finally(() => {
        snapshotPromise = null;
      });
  }
  return snapshotPromise;
}

async function refreshSnapshot(): Promise<IssuesSnapshot> {
  const snapshot = await runSnapshot();
  cachedSnapshot = snapshot;
  return snapshot;
}

function shouldRefreshSnapshot(
  refreshValue: unknown
): boolean {
  if (Array.isArray(refreshValue)) {
    return refreshValue.includes("1") || refreshValue.includes("true");
  }
  return refreshValue === "1" || refreshValue === "true";
}

async function getSnapshotForRequest(
  refreshValue: unknown
): Promise<IssuesSnapshot> {
  if (shouldRefreshSnapshot(refreshValue)) {
    const snapshot = await refreshSnapshot();
    broadcastSnapshot(snapshot);
    return snapshot;
  }
  return getSnapshot();
}

const apiRouter = express.Router();

apiRouter.get("/auth/bootstrap", (_req, res) => {
  const account = null;
  const project = null;
  res.json({
    mode: "none",
    tenant_account_claim_key: "custom:account",
    tenant_project_claim_key: "custom:project",
    account,
    project
  });
});

apiRouter.get("/realtime/bootstrap", (_req, res) => {
  const account = "";
  const project = "";
  const topic = account && project
    ? `projects/${account}/${project}/events`
    : "projects/local/local/events";
  res.json({
    mode: "sse",
    region: "local",
    iot_endpoint: "localhost",
    topic,
    account,
    project
  });
});

apiRouter.get("/config", async (req, res) => {
  try {
    const snapshot = await getSnapshotForRequest(req.query.refresh);
    res.json(snapshot.config);
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

apiRouter.get("/issues", async (_req, res) => {
  try {
    const snapshot = await getSnapshotForRequest(_req.query.refresh);
    res.json(snapshot.issues);
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

apiRouter.get("/issues/:id", async (req, res) => {
  try {
    const snapshot = await getSnapshotForRequest(req.query.refresh);
    const issue = snapshot.issues.find((item) => item.id === req.params.id);
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
const telemetryClients = new Set<express.Response>();

apiRouter.get("/events", async (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();
  res.write("retry: 1000\n\n");

  sseClients.add(res);
  logConsoleEvent("sse-client-connected", { clients: sseClients.size });

  try {
    const snapshot = await getSnapshot();
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
    logConsoleEvent("sse-client-disconnected", { clients: sseClients.size });
  });
});

// Realtime stream alias used by the web client.
apiRouter.get("/events/realtime", async (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();
  res.write("retry: 1000\n\n");

  sseClients.add(res);
  logConsoleEvent("sse-client-connected", {
    clients: sseClients.size,
    stream: "realtime"
  });

  try {
    const snapshot = await getSnapshot();
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
    logConsoleEvent("sse-client-disconnected", {
      clients: sseClients.size,
      stream: "realtime"
    });
  });
});

apiRouter.get("/telemetry/console/events", (req, res) => {
  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.flushHeaders();
  res.write("retry: 1000\n\n");

  telemetryClients.add(res);
  logConsoleEvent("telemetry-client-connected", { clients: telemetryClients.size });

  req.on("close", () => {
    telemetryClients.delete(res);
    logConsoleEvent("telemetry-client-disconnected", { clients: telemetryClients.size });
  });
});

apiRouter.post(
  "/telemetry/console",
  express.text({ type: "*/*", limit: "1mb" }),
  (req, res) => {
    writeConsoleLog({
      type: "telemetry-received",
      at: new Date().toISOString(),
      contentType: classifyContentType(req.headers["content-type"]),
      contentLength: classifyContentLength(req.headers["content-length"])
    });
    let parsed: Record<string, unknown> = {};
    if (typeof req.body === "string" && req.body.length > 0) {
      try {
        parsed = JSON.parse(req.body) as Record<string, unknown>;
      } catch {
        parsed = { raw: req.body };
      }
    } else if (req.body && typeof req.body === "object") {
      parsed = req.body as Record<string, unknown>;
    }
    const payload = {
      ...parsed,
      received_at: new Date().toISOString()
    };
    broadcastTelemetry(payload);
    writeConsoleLog({
      type: "telemetry",
      at: new Date().toISOString(),
      payloadCaptured: false
    });
    res.status(204).end();
  }
);

const wikiRoot = path.join(projectRoot, "wiki");

function getRustKbsPath(): string | null {
  const fromPath = process.env.PATH?.split(path.delimiter).find((dir) => {
    const candidate = path.join(dir, "kbs");
    try {
      return fs.existsSync(candidate);
    } catch {
      return false;
    }
  });
  if (fromPath) {
    return path.join(fromPath, "kbs");
  }
  const release = path.join(repoRoot, "rust", "target", "release", "kbs");
  if (fs.existsSync(release)) {
    return release;
  }
  const debug = path.join(repoRoot, "rust", "target", "debug", "kbs");
  if (fs.existsSync(debug)) {
    return debug;
  }
  return null;
}

function normalizeWikiPath(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    throw new Error("invalid wiki path");
  }
  if (trimmed.startsWith("/") || trimmed.includes(":")) {
    throw new Error("invalid wiki path");
  }
  const replaced = trimmed.replace(/\\/g, "/");
  const parts: string[] = [];
  for (const part of replaced.split("/")) {
    if (part === "" || part === ".") {
      throw new Error("invalid wiki path");
    }
    if (part === "..") {
      throw new Error("invalid wiki path");
    }
    parts.push(part);
  }
  const canonical = parts.join("/");
  if (!canonical.endsWith(".md")) {
    throw new Error("wiki path must end with .md");
  }
  return canonical;
}

function absoluteWikiPath(normalizedPath: string): string {
  return path.join(wikiRoot, normalizedPath);
}

async function collectMarkdownPages(
  dirPath: string,
  relativePrefix: string,
  pages: string[]
): Promise<void> {
  const entries = await fsPromises.readdir(dirPath, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dirPath, entry.name);
    const relative = relativePrefix ? `${relativePrefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) {
      await collectMarkdownPages(full, relative, pages);
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      pages.push(relative.replace(/\\/g, "/"));
    }
  }
}

async function listWikiPages(): Promise<{ pages: string[] }> {
  if (!fs.existsSync(wikiRoot)) {
    return { pages: [] };
  }
  const pages: string[] = [];
  await collectMarkdownPages(wikiRoot, "", pages);
  pages.sort();
  return { pages };
}

async function wikiRenderPage(relativePagePath: string): Promise<string> {
  const rustKbs = getRustKbsPath();
  if (rustKbs) {
    try {
      const { stdout } = await execFileAsync(rustKbs, ["wiki", "render", relativePagePath], {
        cwd: repoRoot,
        env: { ...process.env },
        maxBuffer: 2 * 1024 * 1024
      });
      return stdout.trimEnd();
    } catch (rustError) {
      const err = rustError as Error & { stderr?: string; stdout?: string };
      const detail = [err.stderr, err.stdout, err.message].filter(Boolean).join("\n").trim();
      logConsoleEvent("wiki-render-rust-fallback", { path: relativePagePath, detail });
    }
  }

  const command = kanbusPython ?? "kanbus";
  const args = kanbusPython
    ? [...kanbusPythonArgs, "-m", "kanbus.cli", "wiki", "render", relativePagePath]
    : ["wiki", "render", relativePagePath];
  const { stdout } = await execFileAsync(command, args, {
    cwd: repoRoot,
    env: {
      ...process.env,
      KANBUS_NO_DAEMON: "1",
      PYTHONPATH: kanbusPython ? pythonPath ?? process.env.PYTHONPATH : process.env.PYTHONPATH
    },
    maxBuffer: 2 * 1024 * 1024
  });
  return stdout.trimEnd();
}

apiRouter.get("/wiki/pages", async (_req, res) => {
  try {
    const result = await listWikiPages();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: (error as Error).message });
  }
});

apiRouter.get("/wiki/page", async (req, res) => {
  try {
    const raw = req.query.path;
    if (typeof raw !== "string") {
      res.status(400).json({ error: "invalid wiki path" });
      return;
    }
    const normalized = normalizeWikiPath(raw);
    const absolute = absoluteWikiPath(normalized);
    if (!fs.existsSync(absolute)) {
      res.status(404).json({ error: "wiki page not found" });
      return;
    }
    const content = await fsPromises.readFile(absolute, "utf-8");
    res.json({ path: normalized, content, exists: true });
  } catch (error) {
    const message = (error as Error).message;
    if (message === "invalid wiki path" || message === "wiki path must end with .md") {
      res.status(400).json({ error: message });
      return;
    }
    res.status(500).json({ error: message });
  }
});

apiRouter.post(
  "/wiki/page",
  express.json({ limit: "2mb" }),
  async (req, res) => {
    try {
      const body = req.body as { path?: string; content?: string; overwrite?: boolean };
      const raw = body?.path;
      if (typeof raw !== "string") {
        res.status(400).json({ error: "invalid wiki path" });
        return;
      }
      const normalized = normalizeWikiPath(raw);
      const absolute = absoluteWikiPath(normalized);
      const overwrite = Boolean(body?.overwrite);
      if (fs.existsSync(absolute) && !overwrite) {
        res.status(409).json({ error: "wiki page already exists" });
        return;
      }
      const content = body?.content ?? "# New page\n";
      const parent = path.dirname(absolute);
      await fsPromises.mkdir(parent, { recursive: true });
      const tempPath = `${absolute}.tmp.${Date.now()}.md`;
      await fsPromises.writeFile(tempPath, content, "utf-8");
      await fsPromises.rename(tempPath, absolute);
      res.json({ path: normalized, created: true });
    } catch (error) {
      const message = (error as Error).message;
      if (message === "invalid wiki path" || message === "wiki path must end with .md") {
        res.status(400).json({ error: message });
        return;
      }
      res.status(500).json({ error: message });
    }
  }
);

apiRouter.put(
  "/wiki/page",
  express.json({ limit: "2mb" }),
  async (req, res) => {
    try {
      const body = req.body as { path?: string; content?: string };
      const raw = body?.path;
      if (typeof raw !== "string" || typeof body?.content !== "string") {
        res.status(400).json({ error: "invalid wiki path" });
        return;
      }
      const normalized = normalizeWikiPath(raw);
      const absolute = absoluteWikiPath(normalized);
      if (!fs.existsSync(absolute)) {
        res.status(404).json({ error: "wiki page not found" });
        return;
      }
      const tempPath = `${absolute}.tmp.${Date.now()}.md`;
      await fsPromises.writeFile(tempPath, body.content, "utf-8");
      await fsPromises.rename(tempPath, absolute);
      res.json({ path: normalized, updated: true });
    } catch (error) {
      const message = (error as Error).message;
      if (message === "invalid wiki path" || message === "wiki path must end with .md") {
        res.status(400).json({ error: message });
        return;
      }
      res.status(500).json({ error: message });
    }
  }
);

apiRouter.delete("/wiki/page", async (req, res) => {
  try {
    const raw = req.query.path;
    if (typeof raw !== "string") {
      res.status(400).json({ error: "invalid wiki path" });
      return;
    }
    const normalized = normalizeWikiPath(raw);
    const absolute = absoluteWikiPath(normalized);
    if (!fs.existsSync(absolute)) {
      res.status(404).json({ error: "wiki page not found" });
      return;
    }
    await fsPromises.unlink(absolute);
    res.json({ path: normalized, deleted: true });
  } catch (error) {
    const message = (error as Error).message;
    if (message === "invalid wiki path" || message === "wiki path must end with .md") {
      res.status(400).json({ error: message });
      return;
    }
    res.status(500).json({ error: message });
  }
});

apiRouter.post(
  "/wiki/rename",
  express.json({ limit: "16kb" }),
  async (req, res) => {
    try {
      const body = req.body as { from_path?: string; to_path?: string; overwrite?: boolean };
      const fromRaw = body?.from_path;
      const toRaw = body?.to_path;
      if (typeof fromRaw !== "string" || typeof toRaw !== "string") {
        res.status(400).json({ error: "invalid wiki path" });
        return;
      }
      const fromNormalized = normalizeWikiPath(fromRaw);
      const toNormalized = normalizeWikiPath(toRaw);
      const fromAbsolute = absoluteWikiPath(fromNormalized);
      const toAbsolute = absoluteWikiPath(toNormalized);
      if (!fs.existsSync(fromAbsolute)) {
        res.status(404).json({ error: "wiki page not found" });
        return;
      }
      const overwrite = Boolean(body?.overwrite);
      if (fs.existsSync(toAbsolute) && !overwrite) {
        res.status(409).json({ error: "wiki page already exists" });
        return;
      }
      const toParent = path.dirname(toAbsolute);
      await fsPromises.mkdir(toParent, { recursive: true });
      await fsPromises.rename(fromAbsolute, toAbsolute);
      res.json({ from_path: fromNormalized, to_path: toNormalized, renamed: true });
    } catch (error) {
      const message = (error as Error).message;
      if (message === "invalid wiki path" || message === "wiki path must end with .md") {
        res.status(400).json({ error: message });
        return;
      }
      res.status(500).json({ error: message });
    }
  }
);

apiRouter.post(
  "/wiki/render",
  express.json({ limit: "2mb" }),
  async (req, res) => {
    try {
      const body = req.body as { path?: string; content?: string };
      const raw = body?.path;
      if (typeof raw !== "string") {
        res.status(400).json({ error: "invalid wiki path" });
        return;
      }
      const normalized = normalizeWikiPath(raw);
      const absolute = absoluteWikiPath(normalized);
      const relativePagePath = path.relative(repoRoot, absolute).replace(/\\/g, "/");

      let renderPath = relativePagePath;
      let tempPath: string | null = null;

      if (body?.content != null) {
        tempPath = path.join(wikiRoot, `.tmp.render.${Date.now()}.md`);
        const tempDir = path.dirname(tempPath);
        await fsPromises.mkdir(tempDir, { recursive: true });
        await fsPromises.writeFile(tempPath, body.content, "utf-8");
        renderPath = path.relative(repoRoot, tempPath).replace(/\\/g, "/");
      } else if (!fs.existsSync(absolute)) {
        res.status(404).json({ error: "wiki page not found" });
        return;
      }

      try {
        const rendered = await wikiRenderPage(renderPath);
        res.json({ path: normalized, rendered_markdown: rendered });
      } catch (renderError) {
        const err = renderError as Error & { stderr?: string; stdout?: string };
        const detail = [err.stderr, err.stdout, err.message].filter(Boolean).join("\n").trim() || err.message;
        logConsoleEvent("wiki-render-error", { path: normalized, detail });
        res.status(500).json({ error: detail });
      } finally {
        if (tempPath && fs.existsSync(tempPath)) {
          await fsPromises.unlink(tempPath).catch(() => {});
        }
      }
    } catch (error) {
      const message = (error as Error).message;
      if (message === "invalid wiki path" || message === "wiki path must end with .md") {
        res.status(400).json({ error: message });
        return;
      }
      res.status(500).json({ error: message });
    }
  }
);

app.use("/:account/:project/api", apiRouter);
app.use("/api", apiRouter);

function broadcastSnapshot(snapshot: IssuesSnapshot) {
  const payload = `data: ${JSON.stringify(snapshot)}\n\n`;
  for (const client of sseClients) {
    client.write(payload);
  }
}

function broadcastTelemetry(payload: Record<string, unknown>) {
  const message = `data: ${JSON.stringify(payload)}\n\n`;
  for (const client of telemetryClients) {
    client.write(message);
  }
}

let debounceTimer: NodeJS.Timeout | null = null;
let snapshotRefreshInFlight = false;
let snapshotRefreshQueued = false;

async function runSnapshotRefreshAndBroadcast() {
  if (snapshotRefreshInFlight) {
    snapshotRefreshQueued = true;
    return;
  }
  snapshotRefreshInFlight = true;
  try {
    const refreshStartedAt = Date.now();
    try {
      const snapshot = await refreshSnapshot();
      if (sseClients.size > 0) {
        broadcastSnapshot(snapshot);
      }
      logConsoleEvent("snapshot-broadcast", {
        durationMs: Date.now() - refreshStartedAt,
        clients: sseClients.size
      });
    } catch (error) {
      const payload = {
        error: (error as Error).message,
        updated_at: new Date().toISOString()
      };
      const message = `data: ${JSON.stringify(payload)}\n\n`;
      for (const client of sseClients) {
        client.write(message);
      }
      logConsoleEvent("snapshot-error", {
        durationMs: Date.now() - refreshStartedAt,
        clients: sseClients.size,
        error: (error as Error).message
      });
    }
  } finally {
    snapshotRefreshInFlight = false;
    if (snapshotRefreshQueued) {
      snapshotRefreshQueued = false;
      setImmediate(() => {
        void runSnapshotRefreshAndBroadcast();
      });
    }
  }
}

const configPath = path.join(repoRoot, ".kanbus.yml");
const overridePath = path.join(repoRoot, ".kanbus.override.yml");
const watcher = chokidar.watch([projectRoot, configPath, overridePath], {
  ignoreInitial: true,
  awaitWriteFinish: {
    stabilityThreshold: 200,
    pollInterval: 100
  }
});

watcher.on("all", (eventName, filePath) => {
  logConsoleEvent("fs-change", { event: eventName, path: filePath });
  // Always invalidate cached snapshot so next request sees fresh data.
  cachedSnapshot = null;
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(async () => {
    debounceTimer = null;
    // Avoid expensive snapshot rebuilds when no snapshot SSE clients are attached.
    if (sseClients.size === 0) {
      logConsoleEvent("snapshot-invalidated", { clients: 0 });
      return;
    }
    void runSnapshotRefreshAndBroadcast();
  }, 250);
});

async function startServer(): Promise<void> {
  const port = await resolvePortOrExit({
    desiredPort,
    serviceName: "Kanbus console server",
    envVariable: "CONSOLE_PORT"
  });

  app.listen(port, () => {
    console.log(`Kanbus console server running on ${port}`);
  });
}

void startServer();
