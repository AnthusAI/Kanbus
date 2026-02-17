import express from "express";
import cors from "cors";
import path from "path";
import { execFile } from "child_process";
import { promisify } from "util";
import chokidar from "chokidar";
import { resolvePortOrExit } from "../scripts/resolvePort";
import type { IssuesSnapshot } from "../src/types/issues";

const app = express();
const desiredPort = Number(process.env.CONSOLE_PORT ?? 5174);
const projectRoot = process.env.CONSOLE_PROJECT_ROOT
  ? path.resolve(process.env.CONSOLE_PROJECT_ROOT)
  : null;
if (!projectRoot) {
  throw new Error("CONSOLE_PROJECT_ROOT is required");
}
const repoRoot = path.dirname(projectRoot);
const execFileAsync = promisify(execFile);
const kanbusPython = process.env.KANBUS_PYTHON ?? null;
const pythonPath = process.env.KANBUS_PYTHONPATH
  ? path.resolve(repoRoot, process.env.KANBUS_PYTHONPATH)
  : null;

app.use(
  cors({
    origin: "http://localhost:5173",
    methods: ["GET", "POST"]
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
}

async function runSnapshot(): Promise<IssuesSnapshot> {
  const command = kanbusPython ?? "kanbus";
  const args = kanbusPython
    ? ["-m", "kanbus.cli", "console", "snapshot"]
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
  express.json({ limit: "1mb" }),
  (req, res) => {
    const payload = {
      ...req.body,
      received_at: new Date().toISOString()
    };
    broadcastTelemetry(payload);
    res.status(204).end();
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
  if (debounceTimer) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(async () => {
    debounceTimer = null;
    const refreshStartedAt = Date.now();
    try {
      const snapshot = await refreshSnapshot();
      broadcastSnapshot(snapshot);
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
