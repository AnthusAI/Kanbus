# S3 and DynamoDB in the cloud

In this setup there is no git repository behind the board. The Kanbus API service runs as an AWS Lambda function and stores the board in a private S3 bucket, with a DynamoDB table as a query index. A web application signs users in and renders the board with the shared Kanbus UI. This is how you put a Kanbus board inside a product, for people who will never run `kbs`.

```mermaid
flowchart TB
  browser[Browser: your app with @kanbus/ui]
  gateway[HTTP API with JWT authorizer]
  lambda[Kanbus API Lambda]
  s3[(S3 bucket: canonical issues, events, .kanbus.yml)]
  ddb[(DynamoDB table: catalog for queries)]
  browser -- signed-in requests --> gateway
  gateway --> lambda
  lambda --> s3
  lambda --> ddb
```

S3 holds the same files a git checkout would: `.kanbus.yml`, `project/issues/`, and `project/events/`, under a `tenant/project` prefix. DynamoDB holds only a catalog that makes filtering fast; it can be rebuilt from S3 at any time.

The service is in `services/kanbus-api`. Its full contract is in the [service README](https://github.com/AnthusAI/Kanbus/blob/main/services/kanbus-api/README.md).

## What the API supports today

- Create, read, update, and delete issues; add comments; read an issue's event history.
- Filter by project, type, status, assignee, label, parent, text search, and custom fields.
- Optimistic concurrency: every edit sends the revision it last read and fails with a conflict if someone changed the issue in between.
- Safe retries: every write carries an operation id, and repeating it does not apply the change twice.

It does not yet support setting or changing parents, dependency links, or deleting issues that have children. Projects with policy files or lifecycle hooks configured are refused rather than run without them. A deployment serves at most 8 projects, and a single query may consider at most 1,000 issues, so large boards need narrow filters.

## 1. Try the API on your machine

The same API runs locally against a folder, which is the quickest way to see how it behaves. You need the Rust toolchain and a Kanbus board, such as the one from the [local files](local-files.md) guide.

```bash
git clone https://github.com/AnthusAI/Kanbus.git
cd Kanbus/services/kanbus-api
cargo build --bin kanbus-api-local
```

Start it, pointing `KANBUS_ROOT` at the folder that contains `.kanbus.yml`:

```bash
export KANBUS_BACKEND=file
export KANBUS_ROOT=/path/to/your/repository
export KANBUS_NAMESPACE=acme/website
export KANBUS_LOCAL_TOKEN=choose-a-secret-of-16-or-more-characters
target/debug/kanbus-api-local
# Kanbus API listening at http://127.0.0.1:5175
```

The local server listens on `127.0.0.1` only and accepts one bearer token. It keeps write bookkeeping in a sibling folder named `.<folder>.virtuus`.

In another terminal, read the board and make changes:

```bash
API=http://127.0.0.1:5175
AUTH="Authorization: Bearer choose-a-secret-of-16-or-more-characters"
JSON="Content-Type: application/json"

curl -s $API/api/config -H "$AUTH"
curl -s "$API/api/issues?status=open" -H "$AUTH"

curl -s -X POST $API/api/issues -H "$AUTH" -H "$JSON" \
  -H "X-Operation-Id: $(uuidgen)" \
  -d '{"title":"Created through the API","type":"bug"}'
# {"issue":{"id":"acme-6b3a9b94-...", ...},"revision":"a5cd...","catalog_pending":false}
```

Edits, comments, and deletes also need the revision from the last read, in `If-Match`:

```bash
curl -s -X PATCH $API/api/issues/acme-6b3a9b94-b9ef-41ff-a083-315278fd8cd4 \
  -H "$AUTH" -H "$JSON" -H "X-Operation-Id: $(uuidgen)" -H "If-Match: a5cd..." \
  -d '{"status":"in_progress"}'

curl -s -X POST $API/api/issues/acme-6b3a9b94-b9ef-41ff-a083-315278fd8cd4/comments \
  -H "$AUTH" -H "$JSON" -H "X-Operation-Id: $(uuidgen)" -H "If-Match: <new revision>" \
  -d '{"text":"Seen in production."}'
```

Sending an old revision returns `409` with `revision_conflict`; read the issue again and retry. The files the API writes are ordinary Kanbus files, so `kbs list` in the same folder shows them.

The API reads the folder once when it starts. While it runs, it must be the only writer: changes made with `kbs` in the same folder do not appear in API queries until you restart it.

## 2. Deploy into an Amplify application

The API is not a separate product to sign up for. You add it to an existing Amplify Gen 2 application's backend, which then owns the bucket, table, function, and HTTP API, and deploys them with the rest of the app. The step-by-step reference is [Embed a cloud Kanbus board in an Amplify application](https://github.com/AnthusAI/Kanbus/blob/main/services/kanbus-api/AMPLIFY.md); Prospectus is a working example. In summary:

1. **Build the Lambda.** Pin a Kanbus commit and build the `kanbus-api-lambda` binary with `--features aws` for `x86_64-unknown-linux-musl`, using the Rust version in `services/kanbus-api/rust-toolchain.toml`. Zip it as `bootstrap`.
2. **Declare the resources** in a CDK stack from `backend.createStack(...)`:
   - a private, versioned S3 bucket that blocks public access, requires TLS, and is retained on removal;
   - a DynamoDB table with partition key `scope` and sort key `path` (both strings), on-demand capacity, point-in-time recovery, and the `by_type`, `by_status`, and `by_type_status` indexes;
   - the Lambda (`PROVIDED_AL2023`, handler `bootstrap`, `X86_64`);
   - an HTTP API with a JWT authorizer for your app's user pool, routing `/api/{proxy+}` for GET, POST, PATCH, and DELETE.
3. **Configure the Lambda:**

   ```
   KANBUS_BACKEND=s3
   KANBUS_OBJECT_BUCKET=<bucket name>
   KANBUS_CATALOG_TABLE=<table name>
   KANBUS_NAMESPACE=acme/website
   KANBUS_REQUIRED_GROUP=<the user group allowed to use the board>
   ```

   Signing in is not enough to see the board; users must also be in `KANBUS_REQUIRED_GROUP`.
4. **Scope permissions** to the namespace: S3 access to `acme/website/*` and `_virtuus/acme/website/*`, and DynamoDB access with `LeadingKeys` set to `acme/website`. The reference guide lists the exact conditions.
5. **Publish `.kanbus.yml`** to `acme/website/.kanbus.yml` in the bucket, from a reviewed file in your app's source, for example with a `BucketDeployment` that has `prune: false`.
6. **Allow your app's origin** in CORS, with the `authorization`, `content-type`, `if-match`, and `x-operation-id` headers, and expose `etag`.

Deploy through the app's normal Amplify pipeline.

## 3. Bring in an existing board

To move a board from git into S3, stop all writers, copy `.kanbus.yml` and the project folder (`project/issues/`, `project/events/`) into the namespace prefix unchanged, and rebuild the DynamoDB catalog with Virtuus before you let anyone write. S3 stays the source of truth; rebuilding the catalog never rewrites issue files.

## 4. Render the board

Install `@kanbus/ui` from the tarball attached to the Kanbus GitHub release (it is not on npm) and render `IssueCollection` with the configuration from `GET /api/config` and the issues from `GET /api/issues`. Your app handles sign-in, sends the user's token on each request, generates a new operation id for each user action, and keeps each card's revision for edits. Show revision conflicts to the user rather than retrying silently. See the [UI package README](https://github.com/AnthusAI/Kanbus/blob/main/packages/ui/README.md).

## 5. Check the deployment

Before you let staff write to it, check in a test namespace that:

- requests without a token, and from signed-in users outside the group, are refused;
- a group member can create, reload, edit, and comment on an issue;
- an edit with an old revision returns a conflict;
- retrying a write with the same operation id does not add a second event;
- rebuilding the catalog restores search results without changing any S3 object.

## Next

- Board configuration for your domain (types, statuses, custom fields): [Configuration](../CONFIGURATION.md).
