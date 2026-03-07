# Kanbus Cloud Foundation (Python CDK)

This CDK app provisions the v1 cloud foundation for the Kanbus console backend:

- VPC with application subnets
- EFS for tenant data (`/mnt/data/{account}/{project}`)
- Rust Lambda container runtime (`console_lambda`)
- Regional REST API Gateway proxying to Lambda
- Cognito User Pool + Identity Pool foundation
- API Gateway Cognito authorizer on proxy methods
- IoT IAM policy scaffolding for tenant-scoped topics via principal tags
- GitHub webhook ingress Lambda (`/internal/webhooks/github`) + SQS + DLQ
- Tenant sync worker Lambda (EFS-backed) with IoT publish scaffolding
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
- `IotDataEndpointAddress`
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

## Webhook sync note

Webhook ingress currently expects:

- `X-GitHub-Event: push`
- `X-Hub-Signature-256` HMAC header
- `X-Kanbus-Account` and `X-Kanbus-Project` tenant headers

`GITHUB_WEBHOOK_SECRET` is scaffolded as an environment variable placeholder and
should be replaced with a managed secret before production deployment.
