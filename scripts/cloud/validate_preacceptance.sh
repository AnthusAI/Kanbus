#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

PINNED_NODE_VERSION=""

pin_node_toolchain() {
  local version_file="$ROOT_DIR/.nvmrc"
  [[ -f "$version_file" ]] || return 0
  PINNED_NODE_VERSION="$(tr -d '[:space:]' < "$version_file")"
  [[ -n "$PINNED_NODE_VERSION" ]] || return 0

  local node_dir=""
  if [[ "$PINNED_NODE_VERSION" == v* ]]; then
    node_dir="$HOME/.nvm/versions/node/$PINNED_NODE_VERSION/bin"
  else
    node_dir="$HOME/.nvm/versions/node/v$PINNED_NODE_VERSION/bin"
  fi

  if [[ -x "$node_dir/node" ]]; then
    PATH="$node_dir:$PATH"
    export PATH
  fi
}

require_pinned_node_version() {
  [[ -n "$PINNED_NODE_VERSION" ]] || return 0
  local expected="$PINNED_NODE_VERSION"
  if [[ "$expected" != v* ]]; then
    expected="v$expected"
  fi
  local actual
  actual="$(node -v)"
  [[ "$actual" == "$expected" ]] || {
    echo "Expected Node $expected from .nvmrc, found $actual at $(command -v node)" >&2
    exit 2
  }
}

pin_node_toolchain

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 2
  }
}

require_cmd aws
require_cmd jq
require_cmd curl
require_cmd docker
require_cmd node
require_cmd npm
require_cmd npx

require_pinned_node_version

AWS_PROFILE="${AWS_PROFILE:-anthus}"
AWS_REGION="${AWS_REGION:-us-east-1}"
STACK_NAME="${STACK_NAME:-KanbusCloudFoundation}"
DEFAULT_ACCOUNT="${KANBUS_TEST_ACCOUNT:-anthus}"
DEFAULT_PROJECT="${KANBUS_TEST_PROJECT:-kanbus}"
CURRENT_SYNC_SHA="$(git rev-parse --short=12 HEAD)"

for env_name in \
  KANBUS_TEST_ADMIN_USERNAME \
  KANBUS_TEST_ADMIN_PASSWORD \
  KANBUS_TEST_TENANT_USERNAME \
  KANBUS_TEST_TENANT_PASSWORD \
  KANBUS_TEST_MISMATCH_USERNAME \
  KANBUS_TEST_MISMATCH_PASSWORD; do
  if [[ -z "${!env_name:-}" ]]; then
    echo "Missing required env var: $env_name" >&2
    exit 2
  fi
done

if [[ ! -x "$ROOT_DIR/scripts/cloud/get_cognito_token.sh" ]]; then
  chmod +x "$ROOT_DIR/scripts/cloud/get_cognito_token.sh"
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/cloud-validation/$timestamp"
RESP_DIR="$ARTIFACT_DIR/responses"
CW_DIR="$ARTIFACT_DIR/cloudwatch"
mkdir -p "$RESP_DIR" "$CW_DIR"

SUMMARY_JSON="$ARTIFACT_DIR/summary.json"
cat >"$SUMMARY_JSON" <<JSON
{
  "started_at_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "stack": "$STACK_NAME",
  "region": "$AWS_REGION",
  "profile": "$AWS_PROFILE",
  "gates": {}
}
JSON

log() {
  printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$ARTIFACT_DIR/run.log"
}

set_gate() {
  local gate="$1"
  local status="$2"
  jq --arg g "$gate" --arg s "$status" '.gates[$g] = $s' "$SUMMARY_JSON" >"$SUMMARY_JSON.tmp"
  mv "$SUMMARY_JSON.tmp" "$SUMMARY_JSON"
}

fail_gate() {
  local gate="$1"
  local reason="$2"
  set_gate "$gate" "failed"
  jq --arg g "$gate" --arg r "$reason" '.gate_failures[$g] = $r' "$SUMMARY_JSON" >"$SUMMARY_JSON.tmp"
  mv "$SUMMARY_JSON.tmp" "$SUMMARY_JSON"
  log "FAIL $gate: $reason"
  exit 1
}

pass_gate() {
  local gate="$1"
  set_gate "$gate" "passed"
  log "PASS $gate"
}

run_gate_cmd() {
  local gate="$1"
  local label="$2"
  shift 2
  local logfile="$ARTIFACT_DIR/${gate}-${label}.log"
  log "RUN $gate/$label"
  if ! "$@" >"$logfile" 2>&1; then
    tail -n 120 "$logfile" >&2 || true
    fail_gate "$gate" "$label failed (see $logfile)"
  fi
}

http_status() {
  local url="$1"
  local out_file="$2"
  local header_file="$3"
  shift 3
  curl -sS "$url" "$@" -D "$header_file" -o "$out_file" -w '%{http_code}'
}

log "Artifacts: $ARTIFACT_DIR"
log "Using node: $(command -v node) ($(node -v))"

GATE="gate0"
log "Starting $GATE: environment and stack preflight"
run_gate_cmd "$GATE" docker docker info
run_gate_cmd "$GATE" disk df -h /
run_gate_cmd "$GATE" sts env AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" aws sts get-caller-identity
run_gate_cmd "$GATE" stack env AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" aws cloudformation describe-stacks --stack-name "$STACK_NAME" --output json
cp "$ARTIFACT_DIR/$GATE-stack.log" "$RESP_DIR/stack.json"

STACK_STATUS="$(jq -r '.Stacks[0].StackStatus' "$RESP_DIR/stack.json")"
[[ "$STACK_STATUS" == "UPDATE_COMPLETE" ]] || fail_gate "$GATE" "stack status is $STACK_STATUS"

get_output() {
  local key="$1"
  jq -r --arg k "$key" '.Stacks[0].Outputs[] | select(.OutputKey == $k) | .OutputValue' "$RESP_DIR/stack.json"
}

resolve_lambda_by_prefix() {
  local prefix="$1"
  AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" aws cloudformation list-stack-resources \
    --stack-name "$STACK_NAME" \
    --query 'StackResourceSummaries[?ResourceType==`AWS::Lambda::Function`].[LogicalResourceId,PhysicalResourceId]' \
    --output text | awk -v p="$prefix" '$1 ~ ("^" p) {print $2; exit}'
}

API_BASE="$(get_output ApiBaseUrl)"
USER_POOL_ID="$(get_output UserPoolId)"
USER_POOL_CLIENT_ID="$(get_output UserPoolClientId)"
IDENTITY_POOL_ID="$(get_output IdentityPoolId)"
IOT_ENDPOINT="$(get_output IotDataEndpointAddress)"
MQTT_AUTHORIZER_NAME="$(get_output MqttTokenAuthorizerName)"
MQTT_TOKEN_TABLE_NAME="$(get_output MqttTokenTableName)"
SYNC_QUEUE_URL="$(get_output SyncQueueUrl)"
SYNC_DLQ_ARN="$(get_output SyncDlqArn)"
WEBHOOK_SECRET_ARN="$(get_output GithubWebhookSecretArn)"

for required in \
  API_BASE USER_POOL_ID USER_POOL_CLIENT_ID IDENTITY_POOL_ID \
  IOT_ENDPOINT MQTT_AUTHORIZER_NAME MQTT_TOKEN_TABLE_NAME \
  SYNC_QUEUE_URL SYNC_DLQ_ARN WEBHOOK_SECRET_ARN; do
  [[ -n "${!required:-}" && "${!required}" != "null" ]] || fail_gate "$GATE" "missing output $required"
done
pass_gate "$GATE"

GATE="gate1"
log "Starting $GATE: static/build checks"
run_gate_cmd "$GATE" cloud_pytests bash -c "cd infra/cloud && conda run -n py311 python -m pytest -q tests"
run_gate_cmd "$GATE" rust_lib bash -c "cd rust && cargo test -q --lib"
run_gate_cmd "$GATE" rust_console_lambda bash -c "cd rust && cargo test -q --bin console_lambda"
run_gate_cmd "$GATE" rust_kbsc bash -c "cd rust && cargo test -q --bin kbsc"
run_gate_cmd "$GATE" console_typecheck bash -c "cd apps/console && VITE_PORT=6173 CONSOLE_PORT=6174 npm run -s typecheck"
run_gate_cmd "$GATE" console_build bash -c "cd apps/console && VITE_PORT=6173 CONSOLE_PORT=6174 npm run -s build"
pass_gate "$GATE"

GATE="gate2"
log "Starting $GATE: unauthenticated API/auth contract checks (first public hits, no retries)"
status="$(http_status "${API_BASE%/}/" "$RESP_DIR/gate2-root.html" "$RESP_DIR/gate2-root.headers")"
[[ "$status" == "200" ]] || fail_gate "$GATE" "root status=$status"
grep -qi "<!doctype html>" "$RESP_DIR/gate2-root.html" || fail_gate "$GATE" "root not html shell"

status="$(http_status "${API_BASE%/}/api/auth/bootstrap" "$RESP_DIR/gate2-auth-bootstrap.json" "$RESP_DIR/gate2-auth-bootstrap.headers")"
[[ "$status" == "200" ]] || fail_gate "$GATE" "auth/bootstrap status=$status"
jq -e '.mode == "cognito_pkce"' "$RESP_DIR/gate2-auth-bootstrap.json" >/dev/null || fail_gate "$GATE" "auth/bootstrap mode mismatch"

status="$(http_status "${API_BASE%/}/${DEFAULT_ACCOUNT}/${DEFAULT_PROJECT}/api/config" "$RESP_DIR/gate2-config-unauth.json" "$RESP_DIR/gate2-config-unauth.headers")"
[[ "$status" == "401" ]] || fail_gate "$GATE" "tenant config unauth status=$status"

status="$(http_status "${API_BASE%/}/api/tokens" "$RESP_DIR/gate2-tokens-unauth.json" "$RESP_DIR/gate2-tokens-unauth.headers")"
[[ "$status" == "401" ]] || fail_gate "$GATE" "token api unauth status=$status"
pass_gate "$GATE"

GATE="gate3"
log "Starting $GATE: authenticated API + tenant isolation"
TENANT_JWT="$(AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" "$ROOT_DIR/scripts/cloud/get_cognito_token.sh" \
  --client-id "$USER_POOL_CLIENT_ID" \
  --username "$KANBUS_TEST_TENANT_USERNAME" \
  --password "$KANBUS_TEST_TENANT_PASSWORD")"
MISMATCH_JWT="$(AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" "$ROOT_DIR/scripts/cloud/get_cognito_token.sh" \
  --client-id "$USER_POOL_CLIENT_ID" \
  --username "$KANBUS_TEST_MISMATCH_USERNAME" \
  --password "$KANBUS_TEST_MISMATCH_PASSWORD")"

status="$(http_status "${API_BASE%/}/${DEFAULT_ACCOUNT}/${DEFAULT_PROJECT}/api/config" "$RESP_DIR/gate3-config-tenant.json" "$RESP_DIR/gate3-config-tenant.headers" -H "Authorization: Bearer $TENANT_JWT")"
[[ "$status" == "200" ]] || fail_gate "$GATE" "tenant config auth status=$status"

status="$(http_status "${API_BASE%/}/${DEFAULT_ACCOUNT}/${DEFAULT_PROJECT}/api/config" "$RESP_DIR/gate3-config-mismatch.json" "$RESP_DIR/gate3-config-mismatch.headers" -H "Authorization: Bearer $MISMATCH_JWT")"
[[ "$status" == "403" ]] || fail_gate "$GATE" "tenant mismatch status=$status"

status="$(http_status "${API_BASE%/}/${DEFAULT_ACCOUNT}/${DEFAULT_PROJECT}/api/events?follow=1" "$RESP_DIR/gate3-events-follow.txt" "$RESP_DIR/gate3-events-follow.headers" -H "Authorization: Bearer $TENANT_JWT" --max-time 8)"
[[ "$status" == "200" ]] || fail_gate "$GATE" "events follow status=$status"
grep -qi 'content-type: text/event-stream' "$RESP_DIR/gate3-events-follow.headers" || fail_gate "$GATE" "events follow content-type mismatch"
pass_gate "$GATE"

GATE="gate4"
log "Starting $GATE: token admin + authorizer + CLI parity"
ADMIN_JWT="$(AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" "$ROOT_DIR/scripts/cloud/get_cognito_token.sh" \
  --client-id "$USER_POOL_CLIENT_ID" \
  --username "$KANBUS_TEST_ADMIN_USERNAME" \
  --password "$KANBUS_TEST_ADMIN_PASSWORD")"

CREATE_BODY='{"account":"'"$DEFAULT_ACCOUNT"'","project":"'"$DEFAULT_PROJECT"'","scopes":["subscribe"],"expires_in_days":90}'
status="$(curl -sS -D "$RESP_DIR/gate4-token-create.headers" -o "$RESP_DIR/gate4-token-create.json" -w '%{http_code}' \
  -X POST "${API_BASE%/}/api/tokens" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  --data "$CREATE_BODY")"
[[ "$status" == "201" ]] || fail_gate "$GATE" "token create status=$status"
TOKEN_ID="$(jq -r '.token_id' "$RESP_DIR/gate4-token-create.json")"
TOKEN_VALUE="$(jq -r '.token' "$RESP_DIR/gate4-token-create.json")"
[[ "$TOKEN_ID" != "null" && "$TOKEN_VALUE" != "null" ]] || fail_gate "$GATE" "token create payload missing token fields"

status="$(curl -sS -D "$RESP_DIR/gate4-token-list.headers" -o "$RESP_DIR/gate4-token-list.json" -w '%{http_code}' \
  "${API_BASE%/}/api/tokens" -H "Authorization: Bearer $ADMIN_JWT")"
[[ "$status" == "200" ]] || fail_gate "$GATE" "token list status=$status"
jq -e --arg id "$TOKEN_ID" '.tokens[] | select(.token_id == $id)' "$RESP_DIR/gate4-token-list.json" >/dev/null || fail_gate "$GATE" "created token missing in list"

AUTHORIZE_FN_NAME="$(resolve_lambda_by_prefix MqttTokenAuthorizerHandler)"
[[ -n "$AUTHORIZE_FN_NAME" && "$AUTHORIZE_FN_NAME" != "None" ]] || fail_gate "$GATE" "unable to resolve authorizer function name"

TOKEN_B64="$(printf '%s' "$TOKEN_VALUE" | base64)"
cat >"$RESP_DIR/gate4-authorizer-valid-request.json" <<JSON
{"protocolData":{"mqtt":{"username":"?x-amz-customauthorizer-name=$MQTT_AUTHORIZER_NAME","password":"$TOKEN_B64"}}}
JSON
AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
  aws lambda invoke --function-name "$AUTHORIZE_FN_NAME" \
  --payload "fileb://$RESP_DIR/gate4-authorizer-valid-request.json" \
  "$RESP_DIR/gate4-authorizer-valid-response.json" >"$RESP_DIR/gate4-authorizer-valid-meta.json"
jq -e '.isAuthenticated == true' "$RESP_DIR/gate4-authorizer-valid-response.json" >/dev/null || fail_gate "$GATE" "authorizer valid token denied"

status="$(curl -sS -D "$RESP_DIR/gate4-token-revoke.headers" -o "$RESP_DIR/gate4-token-revoke.json" -w '%{http_code}' \
  -X POST "${API_BASE%/}/api/tokens/$TOKEN_ID/revoke" -H "Authorization: Bearer $ADMIN_JWT")"
[[ "$status" == "200" ]] || fail_gate "$GATE" "token revoke status=$status"
jq -e '.revoked == true' "$RESP_DIR/gate4-token-revoke.json" >/dev/null || fail_gate "$GATE" "token revoke payload mismatch"

AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" \
  aws lambda invoke --function-name "$AUTHORIZE_FN_NAME" \
  --payload "fileb://$RESP_DIR/gate4-authorizer-valid-request.json" \
  "$RESP_DIR/gate4-authorizer-revoked-response.json" >"$RESP_DIR/gate4-authorizer-revoked-meta.json"
jq -e '.isAuthenticated == false' "$RESP_DIR/gate4-authorizer-revoked-response.json" >/dev/null || fail_gate "$GATE" "authorizer accepted revoked token"

run_gate_cmd "$GATE" cli_create bash -c "cd rust && cargo run -q --bin kbs -- cloud token create --base-url '$API_BASE' --id-token '$ADMIN_JWT' --account '$DEFAULT_ACCOUNT' --project '$DEFAULT_PROJECT' --scopes subscribe --days 30"
run_gate_cmd "$GATE" cli_list bash -c "cd rust && cargo run -q --bin kbs -- cloud token list --base-url '$API_BASE' --id-token '$ADMIN_JWT' --account '$DEFAULT_ACCOUNT' --project '$DEFAULT_PROJECT'"
CLI_TOKEN_ID="$(jq -r '.token_id' "$ARTIFACT_DIR/$GATE-cli_create.log" | head -n 1)"
[[ -n "$CLI_TOKEN_ID" && "$CLI_TOKEN_ID" != "null" ]] || fail_gate "$GATE" "unable to parse cli token id"
run_gate_cmd "$GATE" cli_revoke bash -c "cd rust && cargo run -q --bin kbs -- cloud token revoke --base-url '$API_BASE' --id-token '$ADMIN_JWT' '$CLI_TOKEN_ID'"
pass_gate "$GATE"

GATE="gate5"
log "Starting $GATE: webhook -> SQS -> EFS sync -> IoT event"
DISPOSABLE_ACCOUNT="preaccept"
DISPOSABLE_PROJECT="e2e-$(printf '%s' "$timestamp" | tr '[:upper:]' '[:lower:]')"

status="$(curl -sS -D "$RESP_DIR/gate5-token-create.headers" -o "$RESP_DIR/gate5-token-create.json" -w '%{http_code}' \
  -X POST "${API_BASE%/}/api/tokens" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  --data '{"account":"'"$DISPOSABLE_ACCOUNT"'","project":"'"$DISPOSABLE_PROJECT"'","scopes":["subscribe"],"expires_in_days":7}')"
[[ "$status" == "201" ]] || fail_gate "$GATE" "disposable token create status=$status"
DISPOSABLE_TOKEN="$(jq -r '.token' "$RESP_DIR/gate5-token-create.json")"
DISPOSABLE_TOKEN_ID="$(jq -r '.token_id' "$RESP_DIR/gate5-token-create.json")"
[[ "$DISPOSABLE_TOKEN" != "null" ]] || fail_gate "$GATE" "missing disposable token"
[[ "$DISPOSABLE_TOKEN_ID" != "null" ]] || fail_gate "$GATE" "missing disposable token id"

WEBHOOK_SECRET="$(AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" aws secretsmanager get-secret-value --secret-id "$WEBHOOK_SECRET_ARN" --query SecretString --output text)"
PAYLOAD_FILE="$RESP_DIR/gate5-webhook-payload.json"
cat >"$PAYLOAD_FILE" <<JSON
{"ref":"refs/heads/dev","after":"$(git rev-parse --short=12 HEAD)","repository":{"clone_url":"https://github.com/AnthusAI/Kanbus.git"}}
JSON
SIG_HEX="$(WEBHOOK_SECRET="$WEBHOOK_SECRET" python - "$PAYLOAD_FILE" <<'PY'
import hashlib
import hmac
import os
import sys
from pathlib import Path
secret = os.environ["WEBHOOK_SECRET"].encode("utf-8")
payload = Path(sys.argv[1]).read_bytes()
print(hmac.new(secret, payload, hashlib.sha256).hexdigest())
PY
)"
status="$(curl -sS -D "$RESP_DIR/gate5-webhook.headers" -o "$RESP_DIR/gate5-webhook.json" -w '%{http_code}' \
  -X POST "${API_BASE%/}/internal/webhooks/github" \
  -H "X-GitHub-Event: push" \
  -H "X-Hub-Signature-256: sha256=$SIG_HEX" \
  -H "X-Kanbus-Account: $DISPOSABLE_ACCOUNT" \
  -H "X-Kanbus-Project: $DISPOSABLE_PROJECT" \
  -H "Content-Type: application/json" \
  --data-binary "@$PAYLOAD_FILE")"
[[ "$status" == "202" ]] || fail_gate "$GATE" "webhook status=$status"

for _ in {1..30}; do
  ATTRS_JSON="$(AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" aws sqs get-queue-attributes \
    --queue-url "$SYNC_QUEUE_URL" \
    --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
    --output json)"
  echo "$ATTRS_JSON" >"$RESP_DIR/gate5-queue-attrs-last.json"
  visible="$(echo "$ATTRS_JSON" | jq -r '.Attributes.ApproximateNumberOfMessages')"
  inflight="$(echo "$ATTRS_JSON" | jq -r '.Attributes.ApproximateNumberOfMessagesNotVisible')"
  if [[ "${visible:-0}" == "0" && "${inflight:-0}" == "0" ]]; then
    break
  fi
  sleep 2
done
visible="$(jq -r '.Attributes.ApproximateNumberOfMessages' "$RESP_DIR/gate5-queue-attrs-last.json")"
inflight="$(jq -r '.Attributes.ApproximateNumberOfMessagesNotVisible' "$RESP_DIR/gate5-queue-attrs-last.json")"
[[ "${visible:-0}" == "0" && "${inflight:-0}" == "0" ]] || fail_gate "$GATE" "sync queue did not drain (visible=$visible inflight=$inflight)"

SYNC_WORKER_FN="$(resolve_lambda_by_prefix TenantSyncWorker)"
[[ -n "$SYNC_WORKER_FN" && "$SYNC_WORKER_FN" != "None" ]] || fail_gate "$GATE" "unable to resolve sync worker lambda name"
SYNC_LOG_FILE="$CW_DIR/gate5-sync-worker-tail.log"
: >"$SYNC_LOG_FILE"
worker_completed=0
for _ in {1..24}; do
  AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" aws logs tail "/aws/lambda/$SYNC_WORKER_FN" --since 15m >"$SYNC_LOG_FILE" || true
  if grep -q "END RequestId" "$SYNC_LOG_FILE"; then
    worker_completed=1
    break
  fi
  sleep 5
done
[[ "$worker_completed" == "1" ]] || fail_gate "$GATE" "sync worker completion log not observed"
if grep -qE "ERROR|Task timed out|Traceback" "$SYNC_LOG_FILE"; then
  fail_gate "$GATE" "sync worker log contains error markers"
fi

status="$(curl -sS -D "$RESP_DIR/gate5-token-revoke.headers" -o "$RESP_DIR/gate5-token-revoke.json" -w '%{http_code}' \
  -X POST "${API_BASE%/}/api/tokens/$DISPOSABLE_TOKEN_ID/revoke" -H "Authorization: Bearer $ADMIN_JWT")"
[[ "$status" == "200" ]] || fail_gate "$GATE" "disposable token revoke status=$status"
jq -e '.revoked == true' "$RESP_DIR/gate5-token-revoke.json" >/dev/null || fail_gate "$GATE" "disposable token revoke payload mismatch"
pass_gate "$GATE"

GATE="gate6"
log "Starting $GATE: browser realtime hard gate (MQTT primary + exact sync SHA + visible board delta)"
if ! git rev-parse --verify HEAD^ >/dev/null 2>&1; then
  fail_gate "$GATE" "current HEAD has no parent commit for proof-delta validation"
fi
if git diff --quiet HEAD^ HEAD -- .beads/issues.jsonl; then
  fail_gate "$GATE" "current HEAD does not change .beads/issues.jsonl; visible board-delta proof would be weak"
fi
APP_URL="${API_BASE%/}/$DEFAULT_ACCOUNT/$DEFAULT_PROJECT/"
run_gate_cmd "$GATE" browser_install bash -c "cd apps/console && npx playwright install chromium"
run_gate_cmd "$GATE" browser_probe bash -c "cd apps/console && npx -y tsx ../../scripts/cloud/probe_browser_realtime.ts --app_url '$APP_URL' --username '$KANBUS_TEST_TENANT_USERNAME' --password '$KANBUS_TEST_TENANT_PASSWORD' --expected_sync_sha '$CURRENT_SYNC_SHA' --timeout_ms 120000 --event_deadline_ms 60000" &
BROWSER_PROBE_PID=$!
sleep 8

PAYLOAD_FILE="$RESP_DIR/gate6-webhook-payload.json"
cat >"$PAYLOAD_FILE" <<JSON
{"ref":"refs/heads/dev","after":"$CURRENT_SYNC_SHA","repository":{"clone_url":"https://github.com/AnthusAI/Kanbus.git"}}
JSON
SIG_HEX="$(WEBHOOK_SECRET="$WEBHOOK_SECRET" python - "$PAYLOAD_FILE" <<'PY'
import hashlib
import hmac
import os
import sys
from pathlib import Path
secret = os.environ["WEBHOOK_SECRET"].encode("utf-8")
payload = Path(sys.argv[1]).read_bytes()
print(hmac.new(secret, payload, hashlib.sha256).hexdigest())
PY
)"
status="$(curl -sS -D "$RESP_DIR/gate6-webhook.headers" -o "$RESP_DIR/gate6-webhook.json" -w '%{http_code}' \
  -X POST "${API_BASE%/}/internal/webhooks/github" \
  -H "X-GitHub-Event: push" \
  -H "X-Hub-Signature-256: sha256=$SIG_HEX" \
  -H "X-Kanbus-Account: $DEFAULT_ACCOUNT" \
  -H "X-Kanbus-Project: $DEFAULT_PROJECT" \
  -H "Content-Type: application/json" \
  --data-binary "@$PAYLOAD_FILE")"
[[ "$status" == "202" ]] || fail_gate "$GATE" "failed to enqueue browser probe webhook (status=$status)"

if ! wait "$BROWSER_PROBE_PID"; then
  fail_gate "$GATE" "browser realtime probe failed (likely MQTT auth/connect path)"
fi
pass_gate "$GATE"

jq --arg finished "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.finished_at_utc = $finished | .result = "passed"' "$SUMMARY_JSON" >"$SUMMARY_JSON.tmp"
mv "$SUMMARY_JSON.tmp" "$SUMMARY_JSON"
log "All gates passed."
log "Summary: $SUMMARY_JSON"
