# Kanbus Cloud Foundation (Python CDK)

This CDK app provisions the v1 cloud foundation for the Kanbus console backend:

- VPC with application subnets
- EFS for tenant data (`/mnt/data/{account}/{project}`)
- Rust Lambda container runtime (`console_lambda`)
- Regional REST API Gateway proxying to Lambda
- Cognito User Pool + Identity Pool foundation
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
- `IdentityPoolId`
- `IotDataEndpointAddress`
- `TenantEfsFileSystemId`
- `TenantEfsAccessPointId`
- `TenantEfsMountPath`
- `TenantRootTemplate`
