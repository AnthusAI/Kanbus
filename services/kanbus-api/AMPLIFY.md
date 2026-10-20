# Embed a cloud Kanbus board in an Amplify application

For a plain CDK deployment without Amplify, use the released [`@kanbus/cdk` construct](../../packages/cdk/README.md), which bundles the Lambda package and creates every resource below.

Use the existing Amplify Gen 2 backend as the deployment owner. The application
composes the Kanbus Lambda, private canonical bucket, supplemental catalog and
authenticated HTTP API in a CDK stack returned by `backend.createStack(...)`.
Amplify deploys that stack with the application's normal branch deployment.
There is no separate Kanbus account bootstrap or manually maintained runtime role.

Prospectus is the deployed reference composition:
[backend factory](https://github.com/AnthusAI/Prospectus/blob/main/amplify/create-backend.ts),
[CDK resources](https://github.com/AnthusAI/Prospectus/blob/main/infra/lib/prospectus-backend.ts),
[immutable sources](https://github.com/AnthusAI/Prospectus/blob/main/source-lock.json),
and [Linux packaging](https://github.com/AnthusAI/Prospectus/blob/main/infra/scripts/build-backend.sh).
Its Accounts directory, CRM branding and optional inquiry intake are separate
application features; they are not required to embed a board.
Prospectus's account assertions and branch-helper role customizations are its own
deployment policy. A consumer uses its existing Amplify deployment connection and
normal generated CDK resource roles.

## Package the shared service

Pin an immutable Kanbus Git commit containing `services/kanbus-api`, rather than
copying its handlers into the application. This service is currently consumed from
Git; it is not a published Cargo application package. Its Cargo lockfile pins the
shared Virtuus store. Keep the UI version/commit in the same application source
lock and install the released `@kanbus/ui` tarball from the Kanbus GitHub release.
Do not assume that the package is available on npm.

On the Linux CI builder, install the exact compiler from this service's
`rust-toolchain.toml` and its `x86_64-unknown-linux-musl` target. With `musl-gcc`
and the normal C build tools available:

```sh
(cd services/kanbus-api && cargo build --locked --release \
  --target x86_64-unknown-linux-musl --bin kanbus-api-lambda --features aws)
mkdir -p .artifacts/kanbus
cp services/kanbus-api/target/x86_64-unknown-linux-musl/release/kanbus-api-lambda \
  .artifacts/kanbus/bootstrap
chmod 755 .artifacts/kanbus/bootstrap
(cd .artifacts/kanbus && zip -X bootstrap.zip bootstrap)
```

If `CARGO_TARGET_DIR` is set, take the executable from that directory instead.
Pass the zip to CDK `lambda.Code.fromAsset(...)`. Use `PROVIDED_AL2023`, handler
`bootstrap`, and `X86_64`; the zip contains the executable at its root. Build and
test before the normal `ampx pipeline-deploy` step in `amplify.yml`. The reference
builder records source SHAs, compiler, target and artifact checksum.

## Declare resources in the Amplify backend

Create these resources in source, alongside the application's existing auth:

| Resource | Required contract |
| --- | --- |
| S3 | Private, block public access, TLS required, versioned; retain canonical records when removing the app. |
| DynamoDB | String partition key `scope`, string sort key `path`, on-demand capacity; retain and enable recovery. |
| `by_type` GSI | String partition key `type_scope`, string sort key `path`, projection ALL. |
| `by_status` GSI | String partition key `status_scope`, string sort key `path`, projection ALL. |
| `by_type_status` GSI | String partition key `type_status_scope`, string sort key `path`, projection ALL. |
| Lambda | Packaged shared service; bounded timeout/memory and CloudWatch log retention. |
| HTTP API | JWT authorizer with the intended issuer and browser client audience; authenticated `/{tenant}/{project}/api/{proxy+}` and `/{tenant}/api/issues` GET/POST/PATCH/DELETE integration. |

Set Lambda environment variables `KANBUS_BACKEND=s3`, `KANBUS_OBJECT_BUCKET`, and
`KANBUS_CATALOG_TABLE`. Board access is granted by Cognito groups named
`kanbus:<tenant>/<project>` (one board) or `kanbus:<tenant>/*` (every board of the
tenant, to be used sparingly). The JWT gateway verifies tokens; Kanbus derives board
grants only from those verified group claims. A successful Google login alone does
not assign board access. Reuse the app's Google
authentication configuration; Kanbus does not require its own Google OAuth client
or secret. Shared Cognito across products is an application decision.

Let CDK create the Lambda execution role and invocation permission. Scope runtime
S3 list access to `brand/project/*` and `_virtuus/brand/project/*`, and object
Get/Put/Delete access to those two prefixes. Scope DynamoDB GetItem/PutItem/
DeleteItem/Query to the table and `LeadingKeys=brand/project`. Index Query access
uses `brand/project#type#*` for `by_type` and `by_type_status`, and
`brand/project#status#*` for `by_status`. The reference construct contains these
exact conditions. Runtime code needs neither IAM administration nor bucket/table
creation permissions. An existing Amplify service connection still needs its
normal authority to deploy the declared backend resources.

Service callers (optional): add a second HTTP API (or stage) with `AWS_IAM` authorization on the same two route patterns and the same Lambda, and set `KANBUS_SERVICE_PRINCIPALS` on the Lambda to a JSON array of `{"role_arn","tenants","provision","delegate_actor"}` entries (format and semantics in README.md, "Service callers"). Grant the calling role `execute-api:Invoke` on that API only.

Trust boundary: the Lambda trusts the authorizer context in its event, so `lambda:InvokeFunction` must be granted only to the two API Gateway APIs and to explicitly trusted roles. A direct invoker is fully trusted.

For cross-origin frontend hosting, allow only the app origin and the API methods
above, with `authorization`, `content-type`, `if-match`, `x-operation-id` request
headers and exposed `etag`. Keep the browser's API URL and auth identifiers in
Amplify outputs; never put AWS credentials or Google secrets in frontend config.

## Configure the domain and render the board

Keep initial domain configuration in the application's source and publish it as
part of the same backend deployment. For example, the standard CDK S3 deployment
construct can publish the reviewed configuration to a newly provisioned namespace:

```ts
import { readFileSync } from "node:fs";
import { BucketDeployment, Source } from "aws-cdk-lib/aws-s3-deployment";

new BucketDeployment(stack, "BoardConfiguration", {
  destinationBucket: objects,
  destinationKeyPrefix: namespace,
  sources: [Source.data(".kanbus.yml", readFileSync("config/board.kanbus.yml", "utf8"))],
  prune: false,
  retainOnDelete: true,
});
```

Here `objects` is the canonical bucket and `namespace` is the same `brand/project`
used by the Lambda. `prune: false` preserves issue/event objects on updates.
Treat changes to this source-owned configuration as reviewed domain migrations;
do not deploy conflicting UI/API workflow definitions. The reference Prospectus
deployment predates this automatic configuration seed and has an already populated
configuration object; cloning its infrastructure alone does not seed that object.

For existing records, import the ordinary folder into the canonical namespace with
writers quiesced: `.kanbus.yml` plus the configured project directory and normal
issue/event paths. Rebuild the supplemental catalog using Virtuus before enabling
writers. Configure the app's domain through Kanbus types, statuses, transitions
and custom values, rather than adding CRM-specific service routes. S3 remains
canonical; a catalog rebuild must not rewrite canonical bytes.

Render the shared UI board using the same configuration and authenticated API
adapter as the standalone Kanbus UI. Keep host navigation, sign-in and branding in
the application shell. Preserve opaque revisions on loaded cards; send a fresh
UUID operation ID for each user action and `If-Match` for edits/comments/deletes.
Display revision conflicts and `catalog_pending` explicitly. See the
[API contract and acceptance limits](README.md) before choosing board size and
query filters. Public contact forms require a separately reviewed intake adapter;
the staff board API is not a public form endpoint.

## Verify a consumer before enabling staff writes

Run the service's all-feature tests and the UI behavior tests in CI, then synthesize
the actual Amplify backend and review namespace/index/auth boundaries. In a test
namespace verify: anonymous requests fail; an authenticated nonmember fails; an
explicit member can create, reload, edit and comment; a stale revision conflicts;
an identical operation retry does not duplicate history; a rebuild restores catalog
entries without changing canonical bytes. Test domain-specific statuses through
the rendered board. Keep live test data separate from production prospects.

Deploy the reviewed application commit through its existing Amplify main branch
pipeline. No console-created side app, manual runtime role edits or separate
deployment of a copied Kanbus backend is required.
