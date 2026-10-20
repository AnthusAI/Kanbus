import assert from "node:assert/strict";
import { test } from "node:test";
import { createKanbusApiClient, KanbusApiError, newOperationId } from "../src/index.js";
import { createFakeFetch } from "./fakeFetch.js";

const operationId = "11111111-1111-4111-8111-111111111111";

function clientFor(status: number, body: unknown, extra: Record<string, unknown> = {}) {
  const fake = createFakeFetch(status, body);
  const client = createKanbusApiClient({ baseUrl: "https://api.example.com/", fetch: fake.fetch, ...extra });
  return { fake, board: client.board("acme", "crm"), client };
}

test("newOperationId returns distinct UUIDs", () => {
  const first = newOperationId();
  assert.match(first, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.notEqual(first, newOperationId());
});

test("getConfig requests the board config route and sends host headers", async () => {
  const { fake, board } = clientFor(200, { actor_id: "a" }, { headers: async () => ({ Authorization: "Bearer t" }) });
  const configuration = await board.getConfig();
  assert.equal(configuration.actor_id, "a");
  assert.equal(fake.requests[0].url, "https://api.example.com/acme/crm/api/config");
  assert.equal(fake.requests[0].method, "GET");
  assert.equal(fake.requests[0].headers.Authorization, "Bearer t");
});

test("synchronous header providers are supported", async () => {
  const { fake, board } = clientFor(200, {}, { headers: () => ({ "x-test": "1" }) });
  await board.getConfig();
  assert.equal(fake.requests[0].headers["x-test"], "1");
});

test("provision sends operation id and optional configuration text", async () => {
  const withConfiguration = clientFor(201, { actor_id: "a" });
  await withConfiguration.board.provision({ operationId, configuration: "project_key: crm\n" });
  const request = withConfiguration.fake.requests[0];
  assert.equal(request.method, "PUT");
  assert.equal(request.url, "https://api.example.com/acme/crm/api/config");
  assert.equal(request.headers["X-Operation-Id"], operationId);
  assert.deepEqual(request.body, { configuration: "project_key: crm\n" });

  const withoutConfiguration = clientFor(201, { actor_id: "a" });
  await withoutConfiguration.board.provision({ operationId });
  assert.equal(withoutConfiguration.fake.requests[0].body, undefined);
});

test("listIssues serializes every query parameter and field predicates as JSON", async () => {
  const { fake, board } = clientFor(200, { issues: [], next_cursor: null, cost: {} });
  await board.listIssues({
    type: ["task", "bug"],
    status: "open",
    assignee: "me",
    label: "x y",
    parent: "p-1",
    search: "a&b",
    sort: "updated_at",
    limit: 5,
    cursor: "c",
    fields: [{ field: "custom.score", operator: "gte", value: 3 }],
  });
  const url = new URL(fake.requests[0].url);
  assert.equal(url.pathname, "/acme/crm/api/issues");
  assert.equal(url.searchParams.get("type"), "task,bug");
  assert.equal(url.searchParams.get("status"), "open");
  assert.equal(url.searchParams.get("assignee"), "me");
  assert.equal(url.searchParams.get("label"), "x y");
  assert.equal(url.searchParams.get("parent"), "p-1");
  assert.equal(url.searchParams.get("search"), "a&b");
  assert.equal(url.searchParams.get("sort"), "updated_at");
  assert.equal(url.searchParams.get("limit"), "5");
  assert.equal(url.searchParams.get("cursor"), "c");
  assert.deepEqual(JSON.parse(url.searchParams.get("fields") as string), [
    { field: "custom.score", operator: "gte", value: 3 },
  ]);
});

test("listIssues with an empty query adds no query string", async () => {
  const { fake, board } = clientFor(200, { issues: [], next_cursor: null, cost: {} });
  await board.listIssues({});
  assert.equal(fake.requests[0].url, "https://api.example.com/acme/crm/api/issues");
});

test("listAcrossBoards uses the tenant route with explicit projects", async () => {
  const { fake, client } = clientFor(200, { issues: [], next_cursor: null, cost: {} });
  await client.listAcrossBoards("acme", ["crm", "ops"], { status: "open" });
  const url = new URL(fake.requests[0].url);
  assert.equal(url.pathname, "/acme/api/issues");
  assert.equal(url.searchParams.get("projects"), "crm,ops");
  assert.equal(url.searchParams.get("status"), "open");
});

test("path segments are percent-encoded", async () => {
  const fake = createFakeFetch(200, {});
  const client = createKanbusApiClient({ baseUrl: "https://h", fetch: fake.fetch });
  await client.board("a/b", "c d").getIssue("x/y?z#1");
  assert.equal(fake.requests[0].url, "https://h/a%2Fb/c%20d/api/issues/x%2Fy%3Fz%231");
});

test("getIssue and getEvents use read routes without write headers", async () => {
  const { fake, board } = clientFor(200, {});
  await board.getIssue("crm-1");
  await board.getEvents("crm-1");
  assert.equal(fake.requests[0].url, "https://api.example.com/acme/crm/api/issues/crm-1");
  assert.equal(fake.requests[1].url, "https://api.example.com/acme/crm/api/issues/crm-1/events");
  assert.equal(fake.requests[0].headers["X-Operation-Id"], undefined);
});

test("createIssue posts fields with operation id and optional actor", async () => {
  const { fake, board } = clientFor(201, { issue: {}, revision: "r", catalog_pending: false });
  await board.createIssue({ title: "T", type: "task" }, { operationId, actor: "chatticus:user:1" });
  const request = fake.requests[0];
  assert.equal(request.method, "POST");
  assert.equal(request.url, "https://api.example.com/acme/crm/api/issues");
  assert.equal(request.headers["X-Operation-Id"], operationId);
  assert.equal(request.headers["X-Kanbus-Actor"], "chatticus:user:1");
  assert.equal(request.headers["If-Match"], undefined);
  assert.deepEqual(request.body, { title: "T", type: "task" });
});

test("createIssue omits the actor header when no actor is given", async () => {
  const { fake, board } = clientFor(201, {});
  await board.createIssue({ title: "T", type: "task" }, { operationId });
  assert.equal(fake.requests[0].headers["X-Kanbus-Actor"], undefined);
});

test("updateIssue patches with If-Match", async () => {
  const { fake, board } = clientFor(200, {});
  await board.updateIssue("crm-1", { status: "closed" }, { operationId, ifMatch: "rev1" });
  const request = fake.requests[0];
  assert.equal(request.method, "PATCH");
  assert.equal(request.headers["If-Match"], "rev1");
  assert.deepEqual(request.body, { status: "closed" });
});

test("deleteIssue sends If-Match and no body", async () => {
  const { fake, board } = clientFor(200, { deleted: true, issue_id: "crm-1", catalog_pending: false });
  await board.deleteIssue("crm-1", { operationId, ifMatch: "rev1", actor: "a:b:c" });
  const request = fake.requests[0];
  assert.equal(request.method, "DELETE");
  assert.equal(request.body, undefined);
  assert.equal(request.headers["If-Match"], "rev1");
  assert.equal(request.headers["X-Kanbus-Actor"], "a:b:c");
});

test("addComment posts only text with If-Match", async () => {
  const { fake, board } = clientFor(201, {});
  await board.addComment("crm-1", "hello", { operationId, ifMatch: "rev1" });
  const request = fake.requests[0];
  assert.equal(request.url, "https://api.example.com/acme/crm/api/issues/crm-1/comments");
  assert.deepEqual(request.body, { text: "hello" });
  assert.equal(request.headers["If-Match"], "rev1");
});

test("board lifecycle routes", async () => {
  const { fake, board } = clientFor(200, {});
  await board.archive({ operationId });
  await board.restore({ operationId });
  await board.purge({ operationId });
  assert.deepEqual(
    fake.requests.map((request) => [request.method, request.url]),
    [
      ["POST", "https://api.example.com/acme/crm/api/board/archive"],
      ["POST", "https://api.example.com/acme/crm/api/board/restore"],
      ["DELETE", "https://api.example.com/acme/crm/api/board"],
    ],
  );
  assert.equal(fake.requests[2].headers["X-Operation-Id"], operationId);
});

test("error responses become KanbusApiError with status, code and message", async () => {
  const { board } = clientFor(409, { error: "revision_conflict", message: "The record changed." });
  await assert.rejects(board.updateIssue("i", {}, { operationId, ifMatch: "r" }), (error: unknown) => {
    assert.ok(error instanceof KanbusApiError);
    assert.equal(error.status, 409);
    assert.equal(error.code, "revision_conflict");
    assert.equal(error.message, "The record changed.");
    assert.equal(error.isRevisionConflict, true);
    return true;
  });
});

test("query budget errors expose cost", async () => {
  const cost = { limit: "catalog_candidates", consumed: { catalog_requests: 3 } };
  const { board } = clientFor(422, { error: "query_budget_exceeded", message: "m", cost });
  await assert.rejects(board.listIssues(), (error: unknown) => {
    assert.ok(error instanceof KanbusApiError);
    assert.deepEqual(error.cost, cost);
    return true;
  });
});

test("gateway errors without the Kanbus shape are reported as unrecognized_error", async () => {
  const { board } = clientFor(403, { message: "Forbidden" });
  await assert.rejects(board.getConfig(), (error: unknown) => {
    assert.ok(error instanceof KanbusApiError);
    assert.equal(error.code, "unrecognized_error");
    assert.equal(error.status, 403);
    assert.equal(error.message, "Forbidden");
    return true;
  });
});

test("non-JSON failure bodies still raise KanbusApiError", async () => {
  const fetchImplementation = async () => new Response("<html>bad gateway</html>", { status: 502 });
  const board = createKanbusApiClient({ baseUrl: "https://h", fetch: fetchImplementation }).board("a", "b");
  await assert.rejects(board.getConfig(), (error: unknown) => {
    assert.ok(error instanceof KanbusApiError);
    assert.equal(error.status, 502);
    assert.equal(error.code, "unrecognized_error");
    return true;
  });
});

test("requests are never retried", async () => {
  const { fake, board } = clientFor(503, { error: "storage_unavailable", message: "m" });
  await assert.rejects(board.getConfig());
  assert.equal(fake.requests.length, 1);
});
