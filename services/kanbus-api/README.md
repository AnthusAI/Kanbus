# Kanbus writable application API

For a domain application hosted on Amplify, follow the [shared service composition
and deployment guide](AMPLIFY.md). It reuses the app's existing Amplify backend.

Tracking: kbs-972765; the shared storage initiative records the wider milestone.

The service reuses Kanbus models, configuration and workflow validation. The initial service fails closed for projects with `.policy` files or configured hooks, whose execution is not yet integrated. It never returns runtime credentials or hook commands in browser configuration. Domain apps configure types, statuses and custom values; the API has no CRM-specific routes. The service-specific behavior specification is `features/writable_api.feature`, exercised by Rust integration tests. Parent and dependency writes and deletion of hierarchical issues are supported; see [Relation writes](#relation-writes). Imports must run while API writers are quiesced. Existing CLI implementations are unchanged.

| Method | Route | Contract |
| --- | --- | --- |
| POST | `/{tenant}/{project}/api/board/archive` | Archive a board; see Board lifecycle |
| POST | `/{tenant}/{project}/api/board/restore` | Restore an archived board |
| DELETE | `/{tenant}/{project}/api/board` | Purge an archived board |
| GET | `/{tenant}/{project}/api/config` | Browser-safe board configuration plus authenticated `actor_id` |
| PUT | `/{tenant}/{project}/api/config` | Provision a board (create-if-absent); see Provisioning a board |
| GET | `/{tenant}/{project}/api/issues` | `{issues:[{issue,revision}],next_cursor}` |
| GET | `/{tenant}/api/issues?projects=a,b` | Cross-board list within one tenant; names are explicit, at most 8, and every board must be granted; each entry also carries `project` |
| POST | `/{tenant}/{project}/api/issues` | Plain create fields, including `title`, `type`, optional `status`, `description`, `priority`, `assignee`, `parent`, `labels`, `custom` |
| GET | `/{tenant}/{project}/api/issues/{id}` | `{issue,revision}` |
| PATCH | `/{tenant}/{project}/api/issues/{id}` | Plain changed mutable fields; custom values merge by key |
| DELETE | `/{tenant}/{project}/api/issues/{id}` | Revision checked deletion, `{deleted,issue_id,catalog_pending}`; rejects incoming child/dependency references |
| POST | `/{tenant}/{project}/api/issues/{id}/comments` | `{text}` |
| GET | `/{tenant}/{project}/api/issues/{id}/events` | `{issue_id,events:[...],next_before:null}`; retained audit history remains readable after deletion |

All routes require authentication. All writes require `X-Operation-Id` containing a UUID. PATCH, DELETE and comment writes additionally require `If-Match` with the last opaque revision. A stale revision returns 409. Repeating an identical request with the same operation ID replays its durable receipt; changed input conflicts. Successful writes return `{issue,revision,catalog_pending}`; pending means canonical publication succeeded but supplemental indexing/history repair still requires attention, not that S3 and DynamoDB committed atomically. Error responses have `{error,message}`.

Issue query parameters on a board route are `type` or comma-separated `types`, `status`, `assignee`, `label`, `parent`, `search`, `sort` (`priority` or `updated_at`), `limit`, `cursor`, and `fields`. `fields` is a JSON array of `{field,operator,value}` scalar predicates; operators are `eq`, `lt`, `lte`, `gt`, `gte`. Custom paths begin with `custom.`. Existing Kanbus filters and search semantics are reused. Targeted per-board catalog queries select type/status candidates; current canonical objects are hydrated and residual filters applied. Filtering and deterministic ordering precede paging. The tenant route additionally requires `projects` (explicit names only, no wildcard). Cursors bind to the selected boards and the query; pagination does not promise a snapshot across concurrent writes. The per-query budget is `MAX_PROJECTS_PER_QUERY` (8) boards.

## Relation writes

`parent` and `dependencies` (an array of `{"target", "type"}` with type `blocked-by` or
`relates-to`) are writable on create and `PATCH`; a `PATCH` value replaces the whole field.
The service guarantees, per board:

1. A committed issue's parent exists and satisfies the hierarchy rule.
2. An issue with live children cannot be deleted.
3. Dependency targets exist and dependency types are allowed.
4. An issue that is the target of live dependencies cannot be deleted.

Per-object revisions cannot protect these across records, so the service keeps one control
object per referenced issue, `relations/<issue id>.json`, in the board's control area (not
in the canonical issue tree; the issue JSON format is unchanged). It holds
`children` and `dependents` (entries with `id`, `added_at`, `operation_id`) and
`deleted` with `deleted_at`. Every read-modify-write is conditional on its revision.

Attach (create with a parent or dependency, reparent, add a dependency):

1. Read the target issue; a missing target is `relation_target_missing`. For a parent, check the hierarchy rule (`hierarchy_violation`).
2. Conditionally add the source to the target's record, stamped with the time and the `X-Operation-Id`. A record flagged `deleted` yields `relation_target_missing`.
3. Re-read the target; if it vanished, remove the entry and return `relation_target_missing`.
4. Commit the source issue through the journal.
5. After the commit, conditionally remove the source from the old target's record (best effort).

Delete an issue:

1. Conditionally flag its record `deleted` (creating it, seeded from the canonical issues, if absent). From now on attaches to it fail.
2. For every entry: if the entry's issue still points here, or the entry is younger than `RELATION_LEASE`, abort and unflag with `issue_has_children` or `issue_has_dependents` (up to 10 identifiers listed). Older entries that do not point here are pruned.
3. Delete through the journal, then remove the record. If the journal delete fails the flag is cleared.

An entry without a committed issue behind it is either an in-flight attach or one whose
request crashed, and the two cannot be told apart. `RELATION_LEASE` (15 minutes) is the age
after which it is treated as abandoned. It must exceed the longest request: `@kanbus/cdk`
defaults the function timeout to 15 seconds and refuses more than 30. Consequences: a delete
within the lease after a crashed attach returns `409 issue_has_children`, and retrying after
the lease succeeds; likewise a crashed delete leaves the flag set, and an attach that finds
a flag older than the lease on an existing issue clears it and proceeds. Lease tests inject
the clock through `Api::with_clock`.

A missing record is seeded from one scan of the canonical issues, so relations written by an
offline import are honored the first time the target is touched. An import after a record
exists is not seen; imports must run while API writers are quiesced.

Replays with the same `X-Operation-Id` re-run the idempotent attach and return the
original response. Changing the type of an issue to or from a hierarchy type returns
`409 type_change_unsupported` (a follow-up: it needs the same fencing as attach).

New error codes (all 409 except where noted): `relation_target_missing`,
`hierarchy_violation`, `issue_has_children`, `issue_has_dependents`,
`type_change_unsupported`. `unsupported_relation_mutation` and `issue_referenced` no longer exist.
Dependency validation failures are 400 `invalid_request`.

## Provisioning a board

`PUT /{tenant}/{project}/api/config` creates a board. Only principals with the `provision` capability whose grants cover the board are allowed; everyone else gets the same 403 `forbidden` body as for an ungranted board. `X-Operation-Id` (UUID) is required and idempotent: repeating the same operation and body returns the stored result (200), and a different body under the same operation ID returns 409 `operation_conflict`.

- No body: provisions Kanbus's default configuration, generated by `kanbus::config::default_project_configuration()` serialized exactly as `kbs init` writes `.kanbus.yml`. Its `project_key` is `kanbus` for every board created this way.
- Body `{"configuration": "<.kanbus.yml text>"}`: the text is stored verbatim after it parses and passes `validate_project_configuration`, the same checks the read path applies. Anything else returns 422 `invalid_configuration` with the validation messages.
- If the board already has a configuration, the response is 409 `board_exists`, whether or not the body matches. There is no update path.
- The configuration is written with `WriteCondition::Absent` through the journaled store. No directory objects are needed in S3; issue and event keys are created on first write. Success returns 201 with the same body as `GET /{tenant}/{project}/api/config`.

## Board lifecycle

Chatticus archives a bot's board when the bot is deleted; the archive is purged after `KANBUS_ARCHIVE_RETENTION_DAYS` days, or at once when an owner asks (archive, then purge). All three routes need the `provision` capability with a grant covering the board; other callers get the same 403 `forbidden` body as for an ungranted board. All require `X-Operation-Id` (UUID), take no body, and are idempotent: a replay returns the original result, and a different request under the same ID is 409 `operation_conflict`.

- `POST .../api/board/archive`: the board must exist (404 `not_found`). Returns 200 `{archived_at, purge_after}` with `purge_after = archived_at + KANBUS_ARCHIVE_RETENTION_DAYS`. An archived board returns 409 `board_archived`.
- `POST .../api/board/restore`: 200 `{restored: true}`; 409 `board_not_archived` if the board is not archived, 409 `purge_in_progress` once a purge has begun.
- `DELETE .../api/board`: 200 `{purged: true}`; 409 `board_not_archived` unless archived. It calls `JournaledStore::purge_scope`, which removes every canonical object, catalog row and control object of the board (including `relations/`) except its own purge intent and receipt. A purge is resumable: repeat it with the same operation ID. A different ID while one is unfinished is 409 `purge_in_progress`. After a purge every route returns 404 `not_found` and `PUT .../api/config` provisions the board again from scratch.

While a board is archived, members and non-provisioning services get 404 `not_found` on every route (identical to a board that does not exist). Provisioning services may `GET` config, issues and events; every other method returns 409 `board_archived` for everyone, including `PUT config`. The cross-board list answers 404 `not_found` for an explicitly named archived board unless the caller provisions. Tenant names beginning with `_` are reserved and rejected with 400 `invalid_request`.

Settings: `KANBUS_ARCHIVE_RETENTION_DAYS` is required by the Lambda, sweeper and local binaries (a positive integer; Chatticus uses 30) and startup fails with a clear message if it is missing or invalid. Purge must run with writers stopped, which archiving guarantees because every write returns 409 `board_archived`.

### Archive index

Lifecycle state lives in the reserved scope `_kanbus/archives`, as canonical objects, because the object store can list and delete those but not enumerate control state by prefix:

- `markers/<tenant>/<project>.json`: `{archived_at, purge_after, archived_by, ...}` plus the operation that started a purge.
- `index/<purge_after as YYYYMMDDTHHMMSSZ>/<tenant>/<project>.json`: sorts by expiry, so the sweeper lists only the expired prefix instead of tenants or the bucket.
- `receipts/<tenant>/<project>/<sha256 of operation>.json`: recorded outcomes that answer replays; a replay that finds its marker still open finishes the cleanup.

Every board request reads one marker. The Lambda role must reach the `_kanbus/archives/` prefix, which the whole-bucket grant already covers. The local binary keeps this state in a folder named `.<root folder>.archive` beside `KANBUS_ROOT`.

### Sweeper

`kanbus-api-sweeper` (feature `aws`) is a Lambda meant to run on a schedule. It calls `Api::sweep_expired_archives(now)`, which lists the index up to `now`, examines at most `SWEEP_BATCH_LIMIT` (50) entries, removes entries whose board was restored or archived again, and purges the rest through the same code path as the API with an operation ID derived from the board and its archive time (or the operation of an interrupted API purge). It logs counts only. Scheduling it (EventBridge) and its environment are deployment work, tracked in kbs-4818904b; `@kanbus/cdk` does not create it yet.

## Boards and access

One deployment serves every board of an environment. The board a request addresses comes only from the request path (`/{tenant}/{project}/api/...`, parsed from `rawPath` alone, so direct Lambda invocation with a hand-built HTTP API v2 event works). Tenant is the organization id and project is the bot id; both must satisfy the Virtuus scope rules (lowercase letters, digits, `-`, `_`, `.`) or the request is rejected with 400 `invalid_request` before any storage access. A new board needs no redeploy: publishing its `.kanbus.yml` makes it usable immediately, and a granted board without one returns 404 `not_found`, the same body an archived board shows to members.

Access comes only from verified identity. In the cloud, grants come from the verified `cognito:groups` claim (JSON array, API Gateway bracketed space-separated string, or a plain single string). A group named `kanbus:<tenant>/<project>` grants that board; `kanbus:<tenant>/*` grants every board of the tenant and should be used sparingly. Other groups and malformed names are ignored. A verified token with no matching group gets 403; authentication alone grants nothing. A request for a board that is not granted returns the same 403 `forbidden` body whether or not the board exists. The authorization decision is `Principal::allows`, a pure function over the verified grants, so other principal sources can be added without touching routing.

Storage access is narrow: a request touches only the requested boards' object prefixes and catalog keys, and the cross-board list queries each named board's own catalog keys. Canonical keys are unchanged (`<tenant>/<project>/...`), so a role limited to one board's prefixes keeps working.

Runtime selects exactly one backend. Local: `KANBUS_BACKEND=file`, `KANBUS_ROOT`, `KANBUS_TENANT`, `KANBUS_PROJECT`, `KANBUS_LOCAL_TOKEN`, optional `KANBUS_PORT` (5175); the local token is granted exactly that one board. The local binary binds `127.0.0.1` only. Cloud: `KANBUS_BACKEND=s3`, `KANBUS_OBJECT_BUCKET`, `KANBUS_CATALOG_TABLE`. The Lambda consumes API Gateway HTTP API JWT authorizer context; it never decodes bearer tokens itself. Gateway invocation permissions and JWT issuer/audience configuration remain infrastructure responsibilities. No public intake route is provided.

## Service callers

Trusted backend services (for example a control plane in the same AWS account) call the API without a user JWT. They use a second API Gateway HTTP API (or stage) whose routes use `AWS_IAM` authorization (SigV4), pointing at the same Lambda and the same routes. The Lambda picks the authenticator from the verified authorizer context in the event:

- `requestContext.authorizer.jwt`: the user path (Cognito groups to grants).
- `requestContext.authorizer.iam`: the service path.
- Neither, or both: 401.

Configuration is the required deployment setting `KANBUS_SERVICE_PRINCIPALS`, a JSON array with one entry per role:

```json
[
  {"role_arn": "arn:aws:iam::111122223333:role/ControlPlane", "tenants": "*", "provision": false, "delegate_actor": true},
  {"role_arn": "arn:aws:iam::111122223333:role/Reporter", "tenants": ["acme", "globex"]}
]
```

`role_arn` is an IAM role ARN without a path (assumed-role ARNs never carry the path). `tenants` is mandatory: `"*"` for every tenant or a non-empty list of tenant names. `provision` and `delegate_actor` default to false. Unknown fields, invalid JSON, invalid entries and a repeated `role_arn` fail startup with a message naming the problem. An empty or absent variable means no service callers; the user path is unaffected.

The caller identity is `requestContext.authorizer.iam.userArn`. The Lambda accepts only `arn:<partition>:sts::<account>:assumed-role/<name>/<session>`, requires `accountId` to equal the account in the ARN, normalizes it to `arn:<partition>:iam::<account>:role/<name>` (the session name is discarded) and compares it with the configured `role_arn` by exact, case-sensitive equality. Prefix matches, other accounts, other role names and anything not shaped like an assumed-role ARN get 403 `forbidden`, the same body as an ungranted board.

A role mapped with tenants `"*"` is granted every board of every tenant; a tenant list grants every board of those tenants. A service principal's actor is its normalized role ARN, unless it delegates.

### Delegated actor

A role with `delegate_actor` must send `X-Kanbus-Actor` on every request (missing or malformed: 400 `invalid_request`). The value must match `^[a-z0-9-]+:[a-z0-9-]+:[A-Za-z0-9-_.]{1,128}$`, for example `chatticus:user:<uuid>`, `chatticus:bot:<uuid>` or `chatticus:system:task-migration`. It is recorded verbatim as the creator, comment author and event `actor_id`. Any other caller that sends the header, including every user and the local binary, gets 403 `forbidden`: a user can never set an actor.

### Trust boundary

The Lambda trusts the authorizer context in its event. `lambda:InvokeFunction` must therefore be granted only to the two API Gateway APIs and to explicitly trusted roles. A direct invoker is fully trusted: it can hand-build any event, including any identity and actor.

## Migration for single-board deployments

Earlier deployments bound one board with the removed variables `KANBUS_NAMESPACE` and `KANBUS_REQUIRED_GROUP` and served `/api/...`. To migrate (for example Prospectus):

1. Create the Cognito group `kanbus:<tenant>/<project>` and add the members who were in the old required group. This can be done before deploying, so groups and routes change in one deploy with no gap.
2. Remove `KANBUS_NAMESPACE` and `KANBUS_REQUIRED_GROUP` from the Lambda environment.
3. Prefix client routes with `/<tenant>/<project>` (for example `/api/issues` becomes `/<tenant>/<project>/api/issues`), and route `/{tenant}/{project}/api/{proxy+}` at the gateway, plus `GET /{tenant}/api/issues` if clients use the cross-board list. Other routes on the same gateway are unaffected; only the kanbus-api route moves.
4. Local and CI runs replace `KANBUS_NAMESPACE=tenant/project` with `KANBUS_TENANT=tenant` and `KANBUS_PROJECT=project`.

Use `kanbus:<tenant>/*` only for operators who need every board of a tenant.

Query budgets (1,000 catalog candidates, 422 `query_budget_exceeded`, the 2.5 MiB response cap) are unchanged by this migration; they have applied since the service was introduced.

The canonical scope contains `.kanbus.yml` and the configured `project_directory` exactly as a local checkout does. Issues and events retain their normal paths. Raw unknown fields survive edits; unmodified imported objects retain their original bytes. Storage metadata and recovery records live outside the canonical project prefix. DynamoDB contains a supplemental catalog only. Folder import/export and catalog repair belong to the Virtuus storage package.

Build from `services/kanbus-api` so its `rust-toolchain.toml` selects Rust 1.98.1. Put `~/.cargo/bin` first on `PATH` so Cargo also uses the matching rustc/rustdoc proxies. Local: `cargo run --bin kanbus-api-local`. Lambda: `cargo lambda build --release --bin kanbus-api-lambda --features aws`. The repository root compiler may be older than this isolated service requires.

This foundation uses bounded exhaustive query evaluation, not an unbounded search service. A deployment authorizes at most 8 projects; requests accept at most 16 field predicates and 16 selected types, with at most 32 combined project/type query streams. The board accepts at most 1,000 catalog candidates across selected projects before hydrating any card, regardless of response `limit`. The API uses the storage bounded-read accessor: File checks opened-file size and limits reading, while S3 checks Content-Length and bounds stream collection. Each hydration request uses the smaller of 2 MiB and the remaining total request byte allowance, so rejection occurs before unbounded collection. Issue/history/reference scans accept at most 1,000 paths and canonical reads, 2 MiB per canonical object, and 16 MiB total accepted canonical bytes. Queries return `cost` counters (`collected_summaries`, `catalog_candidates_examined`, `catalog_requests`, `listed_paths`, `canonical_objects`, `canonical_bytes`); oversized requests return HTTP 422 `query_budget_exceeded` with the exceeded `cost.limit` and consumed counters. Narrow selections are required for larger boards. History currently scans bounded ordinary event paths and returns the complete accepted history, with no continuation; unrelated history counts toward the budget. Reference scans fail before publication if their budget is exceeded. Imports must be quiesced and fit this API's acceptance limits; raw folder export remains a storage concern.

The explicit cloud CRUD test is `tests/aws_api.rs`, ignored during normal tests. `scripts/run-aws-proof.py` verifies account `682849160744` and the existing private `virtuus-store-proof-20261014-aws01` stack, exports temporary credentials only into the child environment, and runs under a unique `proof-api` namespace. It creates no resources or grants. Run with a fresh `VIRTUUS_TEST_RUN=proof-api-<unique-id>`; canonical configuration and audit history remain inventoried, while the test's issue is conditionally deleted with version history preserved.

The API binds the same 2 MiB canonical read policy to JournaledStore recovery, preflight and projection reads, including durable operation replay. A prior successful receipt remains replayable if an oversized restored object prevents projection repair; `catalog_pending` reports the skipped repair. Default raw storage access for administrative export remains independent.

Cost counters cover board card hydration or event/reference scanning; configuration reads (at most one bounded read per selected project, plus route configuration) and journal recovery control reads are separate. Catalog backend requests and examined candidates include backend fanout/lookahead and are distinct from accepted summaries. Requests additionally stop at 512 reported catalog requests or 32,000 backend candidate rows; one bounded page may cross a threshold before rejection.

Issue identity must match its ordinary filename; mismatched imported records fail closed with `invalid_issue` during point reads/mutations and board hydration. No records are rewritten automatically. All generated canonical audit objects are size-checked before any durable mutation intent or issue publication, including deletion history; an oversized before/after event returns `query_budget_exceeded` with `event_bytes` while retaining the original issue and history.

Responses are capped at 2.5 MiB of compact JSON, leaving room for the HTTP API proxy body-string escaping beneath the synchronous Lambda envelope quota. Matching history that exceeds this response cap returns `query_budget_exceeded` with `response_bytes`; history pagination remains future work. Validation diagnostics are bounded, and the actual gateway envelope serializer applies the same guard to success and error bodies. Storage uses the published `virtuus-store =0.1.0` crate and the locked `virtuus =0.6.1` core shared with Kanbus. Both lockfiles resolve registry checksums; no sibling Virtuus checkout or Git-only storage dependency is required.
