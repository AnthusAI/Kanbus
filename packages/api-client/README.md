# @kanbus/api-client

Typed TypeScript client for the Kanbus writable application API (`services/kanbus-api`). ESM, no runtime dependencies, uses the global `fetch` (Node 18+ and browsers). The server contract is `services/kanbus-api/README.md` and `services/kanbus-api/features/writable_api.feature`.

Install from the GitHub release tarball of an `api-client-v*` tag:

```bash
npm install https://github.com/AnthusAI/Kanbus/releases/download/api-client-v0.1.0/kanbus-api-client-0.1.0.tgz
```

## Creating a client

```ts
import { createKanbusApiClient, newOperationId } from "@kanbus/api-client";

const client = createKanbusApiClient({
  baseUrl: "https://api.example.com",
  headers: async () => ({ Authorization: `Bearer ${await getUserJwt()}` }),
});
const board = client.board("acme", "crm");
```

Options: `baseUrl`, optional `fetch` (injectable for tests or custom transports), optional `headers` (a function returning a header record or a promise of one, called on every request). Authentication and signing are always the host's job through that hook. Headers the client sets itself (`X-Operation-Id`, `If-Match`, `X-Kanbus-Actor`, `content-type`) win over host headers.

## Host with a user JWT (Cognito)

```ts
const board = createKanbusApiClient({
  baseUrl: process.env.KANBUS_API_URL!,
  headers: async () => ({ Authorization: await session.getIdToken() }),
}).board(tenant, project);

const page = await board.listIssues({ status: "open", limit: 25 });
```

## Service host with SigV4 (for example Chatticus)

The client does not depend on any AWS package. Sign inside the `fetch` option, which receives the final URL and request. This example uses `@aws-sdk/signature-v4` for service `execute-api`; install it in the host.

```ts
import { SignatureV4 } from "@aws-sdk/signature-v4";
import { Sha256 } from "@aws-crypto/sha256-js";
import { HttpRequest } from "@aws-sdk/protocol-http";
import { defaultProvider } from "@aws-sdk/credential-provider-node";
import { createKanbusApiClient, newOperationId } from "@kanbus/api-client";

const signer = new SignatureV4({
  service: "execute-api",
  region: process.env.AWS_REGION!,
  credentials: defaultProvider(),
  sha256: Sha256,
});

const signedFetch = async (input: string, init: RequestInit = {}) => {
  const url = new URL(input);
  const headers: Record<string, string> = { host: url.host, ...(init.headers as Record<string, string>) };
  const signed = await signer.sign(
    new HttpRequest({
      method: init.method ?? "GET",
      protocol: url.protocol,
      hostname: url.hostname,
      path: url.pathname,
      query: Object.fromEntries(url.searchParams),
      headers,
      body: init.body as string | undefined,
    }),
  );
  return fetch(input, { ...init, headers: signed.headers });
};

const client = createKanbusApiClient({ baseUrl: process.env.KANBUS_API_URL!, fetch: signedFetch });
const board = client.board(organizationId, botId);
await board.createIssue(
  { title: "Migrate tasks", type: "story" },
  { operationId: newOperationId(), actor: `chatticus:bot:${botId}` },
);
```

The role must be mapped in `KANBUS_SERVICE_PRINCIPALS`. A role with `delegate_actor` must pass `actor` on every write and also on reads that the server checks for it (the header is sent only when `actor` is given; pass it through the `headers` hook for reads). Users and the local binary must not send an actor.

## Board client

All write methods require `operationId`; use `newOperationId()` for a fresh UUID, or reuse the same value to retry safely: the server replays the stored result for an identical request and returns 409 `operation_conflict` if the input changed. The client never retries by itself.

| Method | Route |
| --- | --- |
| `getConfig()` | `GET /{tenant}/{project}/api/config` |
| `provision({ operationId, configuration? })` | `PUT .../api/config` (requires the provision capability; `configuration` is `.kanbus.yml` text) |
| `listIssues(query)` | `GET .../api/issues` |
| `getIssue(id)` | `GET .../api/issues/{id}` |
| `createIssue(input, { operationId, actor? })` | `POST .../api/issues` |
| `updateIssue(id, patch, { operationId, ifMatch, actor? })` | `PATCH .../api/issues/{id}` |
| `deleteIssue(id, { operationId, ifMatch, actor? })` | `DELETE .../api/issues/{id}` |
| `addComment(id, text, { operationId, ifMatch, actor? })` | `POST .../api/issues/{id}/comments` |
| `getEvents(id)` | `GET .../api/issues/{id}/events` |
| `archive({ operationId })` | `POST .../api/board/archive` |
| `restore({ operationId })` | `POST .../api/board/restore` |
| `purge({ operationId })` | `DELETE .../api/board` |

`client.listAcrossBoards(tenant, projects, query)` calls `GET /{tenant}/api/issues?projects=a,b` (at most 8 explicitly named boards, all granted); each entry carries `project`.

`archive`, `restore` and `purge` follow the planned kbs-791a7373 contract and are available once the server ships those routes; until then they fail with 404 `not_found`.

Ids, tenant and project names are percent-encoded into the path.

### Revisions

Every issue read and write returns an opaque `revision`. Pass it as `ifMatch` to update, delete and comment. A stale revision raises `KanbusApiError` with status 409 and code `revision_conflict`; a missing one is 428 `revision_required` (the server requires `If-Match` for comments too).

### Queries

`type` (string or array, sent comma separated), `status`, `assignee`, `label`, `parent`, `search`, `sort` (`priority` or `updated_at`), `limit` (1-100), `cursor`, and `fields`, an array of `{ field: "custom.x", operator: "eq" | "lt" | "lte" | "gt" | "gte", value }` serialized as the JSON the API expects. Pages return `issues`, `next_cursor` and `cost`.

### Errors

Non-2xx responses throw `KanbusApiError` with `status`, `code`, `message` and, for `query_budget_exceeded`, `cost`. Codes as emitted by the server include `forbidden`, `unauthorized`, `not_found`, `invalid_request`, `invalid_issue`, `invalid_configuration`, `configuration_missing`, `revision_required`, `revision_conflict`, `operation_conflict`, `unsupported_relation_mutation`, `query_budget_exceeded`, `board_exists`, and (planned) `board_archived` and `board_not_archived`. A response that does not carry the Kanbus error body (for example a gateway 403) is reported with code `unrecognized_error`.

### Types

Issue and configuration types are defined here rather than imported from `@kanbus/ui`: the API returns `null` for empty `assignee`, `parent` and `closed_at`, plus server fields (`creator`, `dependencies`), so the shapes are not assignable to `KanbanIssue` and `KanbanConfig` without a mapping step. Responses are structurally close, so hosts can map them onto the UI types.

## Development

```bash
npm ci
npm test
```

`npm test` builds, typechecks and runs the `node:test` suite against a fake `fetch`. One end-to-end test runs against `kanbus-api-local` when `KANBUS_API_LOCAL_BINARY` (the built binary) and `KANBUS_API_LOCAL_CONFIGURATION` (a `.kanbus.yml` file) are set; otherwise it is skipped.

## Release

Tag `api-client-v<version>` (matching `package.json`). The `api-client-package` job in `.github/workflows/release.yml` verifies the tag, runs `npm ci` and `npm test`, packs the tarball and creates the GitHub release.
