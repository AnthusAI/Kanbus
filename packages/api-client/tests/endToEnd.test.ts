import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, test } from "node:test";
import { createKanbusApiClient, KanbusApiError, newOperationId } from "../src/index.js";

const binaryPath = process.env.KANBUS_API_LOCAL_BINARY;
const configurationPath = process.env.KANBUS_API_LOCAL_CONFIGURATION;
const skip = binaryPath === undefined || configurationPath === undefined;
const port = 5390 + Math.floor(Math.random() * 100);
const token = "end-to-end-token-0123456789";
let server: ChildProcess | undefined;
let root = "";

before(async () => {
  if (skip) return;
  root = mkdtempSync(join(tmpdir(), "kanbus-api-client-"));
  const board = join(root, "board");
  mkdirSync(board);
  copyFileSync(configurationPath as string, join(board, ".kanbus.yml"));
  server = spawn(binaryPath as string, [], {
    env: {
      ...process.env,
      KANBUS_BACKEND: "file",
      KANBUS_ROOT: board,
      KANBUS_TENANT: "acme",
      KANBUS_PROJECT: "crm",
      KANBUS_LOCAL_TOKEN: token,
      KANBUS_PORT: String(port),
    },
    stdio: "ignore",
  });
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      await fetch(`http://127.0.0.1:${port}/`);
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }
  throw new Error("kanbus-api-local did not start");
});

after(() => {
  server?.kill();
  if (root) rmSync(root, { recursive: true, force: true });
});

test("client round trip against kanbus-api-local", { skip }, async () => {
  const board = createKanbusApiClient({
    baseUrl: `http://127.0.0.1:${port}`,
    headers: () => ({ Authorization: `Bearer ${token}` }),
  }).board("acme", "crm");

  const configuration = await board.getConfig();
  assert.equal(configuration.actor_id, "local-member");

  const created = await board.createIssue({ title: "End to end", type: "story" }, { operationId: newOperationId() });
  assert.equal(created.issue.title, "End to end");
  const identifier = created.issue.id;

  const page = await board.listIssues({ type: "story" });
  assert.ok(page.issues.some((entry) => entry.issue.id === identifier));

  const updated = await board.updateIssue(
    identifier,
    { description: "changed" },
    { operationId: newOperationId(), ifMatch: created.revision },
  );
  assert.equal(updated.issue.description, "changed");

  await assert.rejects(
    board.updateIssue(identifier, { description: "stale" }, { operationId: newOperationId(), ifMatch: created.revision }),
    (error: unknown) => error instanceof KanbusApiError && error.status === 409 && error.code === "revision_conflict",
  );

  const commented = await board.addComment(identifier, "note", {
    operationId: newOperationId(),
    ifMatch: updated.revision,
  });
  assert.equal(commented.issue.comments?.length, 1);

  const events = await board.getEvents(identifier);
  assert.ok(events.events.length >= 2);

  const fetched = await board.getIssue(identifier);
  const deleted = await board.deleteIssue(identifier, {
    operationId: newOperationId(),
    ifMatch: fetched.revision,
  });
  assert.equal(deleted.deleted, true);

  await assert.rejects(
    board.getIssue(identifier),
    (error: unknown) => error instanceof KanbusApiError && error.status === 404 && error.code === "not_found",
  );
});
