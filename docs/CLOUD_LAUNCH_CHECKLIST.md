# Cloud Launch Checklist (Read-Only v1)

This checklist tracks launch readiness for the cloud console runtime epic
`tskl-eo2.5`.

## Scope

- Read-only tenant console APIs from Lambda + EFS
- GitHub webhook sync pipeline
- Realtime via MQTT-over-WSS primary, SSE fallback secondary
- Cognito-backed auth and tenant isolation controls

## Checklist

1. Infrastructure deploy
- [ ] `infra/cloud` stack deploy succeeds in `anthus`.
- [ ] Stack outputs captured in deployment record.
- [ ] EFS mount path and access point verified from Lambda runtime.

2. Auth and isolation
- [x] API routes require Cognito authorizer in template.
- [x] Identity role policy enforces tenant-scoped IoT topic pattern.
- [ ] Live token test confirms cross-tenant API access is denied.
- [ ] Live token test confirms cross-tenant MQTT subscribe is denied.

3. Webhook sync flow
- [x] Webhook handler validates signature + tenant headers (unit tests).
- [x] Queue + DLQ + worker wiring present (template + tests).
- [ ] Live GitHub push produces queue message and worker execution.
- [ ] Live worker sync updates tenant EFS repo and publishes IoT event.
- [ ] DLQ redrive runbook step validated.

4. Realtime console behavior
- [x] Bootstrap endpoint returns MQTT contract fields including WSS URL.
- [x] Frontend attempts MQTT-over-WSS first.
- [x] Frontend falls back to SSE on bootstrap/connect/subscribe failure.
- [ ] Browser receives live event over MQTT in deployed environment.
- [ ] SSE fallback behavior validated under forced MQTT failure in deployed environment.

5. Ops guardrails
- [x] DLQ depth alarm configured.
- [x] Queue age alarm configured.
- [x] Lambda error alarms configured (console/webhook/worker).
- [x] API 4xx alarm configured.
- [x] Runbook committed (`docs/CLOUD_OPS_RUNBOOK.md`).
- [ ] Alarm notification routing validated in cloud account.

6. Final go/no-go
- [ ] E2E path passes: webhook -> queue -> worker -> IoT -> UI.
- [ ] Security/isolation checks signed off.
- [ ] Rollback path rehearsed.
- [ ] Epic `tskl-eo2.5` completion comment links evidence for each DoD item.

## Current Blockers (2026-03-07)

- Deploy-backed validation is blocked by local Docker daemon availability for CDK Lambda container asset build (`tskl-eo2.5.1`).
