# Cloud Ops Runbook (Kanbus Console v1)

This runbook covers deploy, smoke checks, rollback, and incident triage for the
cloud console stack (`infra/cloud`).

## Preconditions

- Python commands run from conda env: `conda run -n py311 ...`
- AWS profile: `anthus`
- Local Docker daemon running (required for Lambda container asset builds)

## Deploy

```bash
cd infra/cloud
AWS_PROFILE=anthus npx cdk synth -a "/opt/anaconda3/bin/conda run -n py311 python app.py"
AWS_PROFILE=anthus npx cdk deploy KanbusCloudFoundation --require-approval never -a "/opt/anaconda3/bin/conda run -n py311 python app.py"
```

Capture outputs:

- `ApiBaseUrl`
- `UserPoolId`
- `UserPoolClientId`
- `IdentityPoolId`
- `IotDataEndpointAddress`
- `TenantEfsFileSystemId`
- `SyncQueueUrl`
- `GithubWebhookSecretArn`

## Smoke Checks

1. API auth + route check:
```bash
curl -i "${API_BASE_URL}${STAGE_PATH}/health"
```

2. Realtime bootstrap contract:
```bash
curl -s "${API_BASE_URL}${STAGE_PATH}/{account}/{project}/api/realtime/bootstrap" | jq .
```

3. Queue wiring:
```bash
AWS_PROFILE=anthus aws sqs get-queue-attributes --queue-url "$SYNC_QUEUE_URL" --attribute-names ApproximateNumberOfMessages ApproximateAgeOfOldestMessage
AWS_PROFILE=anthus aws sqs get-queue-attributes --queue-url "$SYNC_DLQ_URL" --attribute-names ApproximateNumberOfMessages
```

4. Lambda error baseline:
```bash
AWS_PROFILE=anthus aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Errors --dimensions Name=FunctionName,Value=<function-name> --start-time "$(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '15 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --period 300 --statistics Sum
```

## Rollback

1. Re-deploy previously known-good commit:
```bash
git checkout <known-good-commit>
cd infra/cloud
AWS_PROFILE=anthus npx cdk deploy KanbusCloudFoundation --require-approval never -a "/opt/anaconda3/bin/conda run -n py311 python app.py"
```

2. If webhook ingress is noisy, disable ingress route temporarily by adding a
WAF or by rotating `GithubWebhookSecretArn`.

3. Confirm alarms and queue depth return to baseline.

## Alarm Map

- `kanbus-sync-dlq-visible-<env>`: DLQ has messages.
- `kanbus-sync-queue-age-<env>`: sync queue backlog age high.
- `kanbus-console-lambda-errors-<env>`: API Lambda errors > 0.
- `kanbus-webhook-lambda-errors-<env>`: webhook ingress errors > 0.
- `kanbus-sync-worker-errors-<env>`: sync worker errors > 0.
- `kanbus-console-api-4xx-<env>`: elevated client/auth failures and other 4xx responses.

## Incident Triage

1. DLQ alarm firing:
- Inspect DLQ message bodies and attributes.
- Reproduce failure against worker logs.
- Redrive once fix is deployed.

2. Webhook ingress errors:
- Confirm signature header and secret retrieval.
- Confirm tenant headers (`X-Kanbus-Account`, `X-Kanbus-Project`) are valid.

3. Console API 4xx spike:
- Confirm Cognito token issuer/audience values match deployed outputs.
- Confirm tenant route path and IoT topic scope claims.

4. Realtime path degraded:
- Verify `/api/realtime/bootstrap` returns expected endpoint/topic.
- Browser should auto-fallback to SSE when MQTT-over-WSS connect fails.
