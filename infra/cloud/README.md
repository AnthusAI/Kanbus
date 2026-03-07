# Kanbus Cloud Foundation (Python CDK)

This CDK app provisions the v1 cloud foundation for the Kanbus console backend:

- VPC with application subnets
- EFS for tenant data (`/mnt/data/{account}/{project}`)
- Rust Lambda container runtime (`console_lambda`)
- Regional REST API Gateway proxying to Lambda
- Cognito User Pool + Identity Pool foundation
- Cognito Hosted UI PKCE bootstrap outputs for browser login UX
- API Gateway Cognito authorizer on proxy methods
- IoT IAM policy scaffolding for tenant-scoped topics via principal tags
- DynamoDB-backed MQTT API token registry
- IoT Core custom authorizer for CLI MQTT API-token auth
- GitHub webhook ingress Lambda (`/internal/webhooks/github`) + SQS + DLQ
- Tenant sync worker Lambda (EFS-backed) with IoT publish scaffolding
- Token admin Lambda API (`/api/tokens`) for create/list/revoke
- AWS IoT Data endpoint discovery output

## Prerequisites

- Python 3.11 in the `py311` conda env
- Node.js + CDK CLI (`npx cdk` is fine)
- AWS credentials for the target account/profile

## Install dependencies

```bash
cd infra/cloud
conda run -n py311 python -m pip install -r requirements.txt
```

## Synthesize

```bash
cd infra/cloud
AWS_PROFILE=anthus npx cdk synth
```

## Deploy

```bash
cd infra/cloud
AWS_PROFILE=anthus npx cdk deploy
```

## Useful context overrides

```bash
cd infra/cloud
AWS_PROFILE=anthus npx cdk synth \
  -c stack_name=KanbusCloudFoundation \
  -c env_name=dev \
  -c account=123456789012 \
  -c region=us-east-1
```

## Outputs

- `ApiBaseUrl`
- `UserPoolId`
- `UserPoolClientId`
- `UserPoolIssuerUrl`
- `IdentityPoolId`
- `UserPoolHostedUiBaseUrl`
- `IotDataEndpointAddress`
- `MqttTokenAuthorizerName`
- `MqttTokenTableName`
- `TenantEfsFileSystemId`
- `TenantEfsAccessPointId`
- `TenantEfsMountPath`
- `TenantRootTemplate`
- `SyncQueueUrl`
- `SyncQueueArn`
- `SyncDlqArn`

## Tenant isolation note

The authenticated identity role includes IoT subscribe/receive permissions scoped to:

- `projects/${aws:PrincipalTag/account}/${aws:PrincipalTag/project}/events`

This is intentional scaffolding for strict tenant isolation. In v1, your identity provider
mapping flow must set `account` and `project` principal tags for authenticated sessions.

Hosted UI + identity pool principal tag mapping now uses Cognito custom attributes:

- `custom:account`
- `custom:project`

## Webhook sync note

Webhook ingress currently expects:

- `X-GitHub-Event: push`
- `X-Hub-Signature-256` HMAC header
- `X-Kanbus-Account` and `X-Kanbus-Project` tenant headers

The stack provisions a Secrets Manager secret and passes its ARN to webhook ingress.
Rotate this secret and configure GitHub webhook delivery to use the same value.
