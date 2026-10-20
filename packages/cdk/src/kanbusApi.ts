import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { CfnOutput, Duration, RemovalPolicy, Stack, Tags } from "aws-cdk-lib";
import * as apigatewayv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as authorizers from "aws-cdk-lib/aws-apigatewayv2-authorizers";
import * as integrations from "aws-cdk-lib/aws-apigatewayv2-integrations";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";

export interface KanbusUsers {
  readonly issuer: string;
  readonly audiences: string[];
}

export interface KanbusServicePrincipal {
  readonly role: iam.IRole;
  readonly tenants: "*" | string[];
  readonly provision?: boolean;
  readonly delegateActor?: boolean;
}

export interface KanbusApiLambdaProps {
  readonly memorySize?: number;
  readonly timeout?: Duration;
  readonly logRetention?: logs.RetentionDays;
  readonly code?: lambda.Code;
}

export interface KanbusApiProps {
  readonly environmentName: string;
  readonly users?: KanbusUsers;
  readonly servicePrincipals?: KanbusServicePrincipal[];
  readonly lambda?: KanbusApiLambdaProps;
  readonly removalPolicy?: RemovalPolicy;
  readonly createOutputs?: boolean;
}

const ENVIRONMENT_NAME_PATTERN = /^[a-z][a-z0-9-]{0,31}$/;
const MINIMUM_MEMORY_MEGABYTES = 128;
const MAXIMUM_MEMORY_MEGABYTES = 3008;
const MAXIMUM_TIMEOUT_SECONDS = 30;
const DEFAULT_MEMORY_MEGABYTES = 512;
const DEFAULT_TIMEOUT_SECONDS = 15;
const ROUTE_METHODS = [
  apigatewayv2.HttpMethod.GET,
  apigatewayv2.HttpMethod.POST,
  apigatewayv2.HttpMethod.PATCH,
  apigatewayv2.HttpMethod.DELETE,
];
const ROUTE_PATHS = ["/{tenant}/{project}/api/{proxy+}", "/{tenant}/api/issues"];
const INDEX_DEFINITIONS = [
  { indexName: "by_type", partitionKeyName: "type_scope" },
  { indexName: "by_status", partitionKeyName: "status_scope" },
  { indexName: "by_type_status", partitionKeyName: "type_status_scope" },
];

function bundledLambdaZipPath(): string {
  return resolve(__dirname, "..", "..", "assets", "kanbus-api-lambda.zip");
}

function resolveLambdaCode(override: lambda.Code | undefined): lambda.Code {
  if (override) {
    return override;
  }
  const zipPath = bundledLambdaZipPath();
  if (!existsSync(zipPath)) {
    throw new Error(
      `The bundled Lambda package kanbus-api-lambda.zip was not found at ${zipPath}. ` +
        "Install @kanbus/cdk from a Kanbus release tarball, which includes it.",
    );
  }
  return lambda.Code.fromAsset(zipPath);
}

function validateProps(props: KanbusApiProps): void {
  if (!ENVIRONMENT_NAME_PATTERN.test(props.environmentName)) {
    throw new Error(
      "environmentName must start with a lowercase letter and contain only lowercase letters, digits and hyphens (maximum 32 characters).",
    );
  }
  const principals = props.servicePrincipals ?? [];
  if (!props.users && principals.length === 0) {
    throw new Error("KanbusApi requires at least one of users or servicePrincipals.");
  }
  const seenRoles = new Set<iam.IRole>();
  for (const principal of principals) {
    const validTenants =
      principal.tenants === "*" ||
      (Array.isArray(principal.tenants) &&
        principal.tenants.length > 0 &&
        principal.tenants.every((tenant) => tenant.length > 0));
    if (!validTenants) {
      throw new Error('Each service principal needs tenants of "*" or a non-empty list of tenant names.');
    }
    if (seenRoles.has(principal.role)) {
      throw new Error("A role may appear in servicePrincipals only once.");
    }
    seenRoles.add(principal.role);
  }
  if (props.users && (props.users.audiences.length === 0 || props.users.issuer.length === 0)) {
    throw new Error("users requires an issuer and at least one audience.");
  }
  const memorySize = props.lambda?.memorySize;
  if (
    memorySize !== undefined &&
    (memorySize < MINIMUM_MEMORY_MEGABYTES || memorySize > MAXIMUM_MEMORY_MEGABYTES)
  ) {
    throw new Error(
      `lambda.memorySize must be between ${MINIMUM_MEMORY_MEGABYTES} and ${MAXIMUM_MEMORY_MEGABYTES} megabytes.`,
    );
  }
  const timeout = props.lambda?.timeout;
  if (timeout !== undefined && timeout.toSeconds() > MAXIMUM_TIMEOUT_SECONDS) {
    throw new Error(
      `lambda.timeout must not exceed ${MAXIMUM_TIMEOUT_SECONDS} seconds, the HTTP API integration limit.`,
    );
  }
}

/**
 * Deploys the Kanbus API service: a private versioned bucket, the catalog table,
 * the bundled Lambda and one or two HTTP APIs. It creates no stacks and no
 * cross-stack references, so it can live in an existing per-environment stack.
 */
export class KanbusApi extends Construct {
  public readonly bucket: s3.IBucket;
  public readonly table: dynamodb.ITable;
  public readonly function: lambda.IFunction;
  public readonly userApi?: apigatewayv2.HttpApi;
  public readonly serviceApi?: apigatewayv2.HttpApi;
  public readonly userApiUrl?: string;
  public readonly serviceApiUrl?: string;

  public constructor(scope: Construct, id: string, props: KanbusApiProps) {
    super(scope, id);
    validateProps(props);
    const removalPolicy = props.removalPolicy ?? RemovalPolicy.RETAIN;
    const bucket = this.createBucket(removalPolicy);
    const table = this.createTable(removalPolicy);
    const logGroup = new logs.LogGroup(this, "LogGroup", {
      retention: props.lambda?.logRetention ?? logs.RetentionDays.THREE_MONTHS,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    const functionRole = this.createFunctionRole(bucket, table, logGroup);
    const servicePrincipals = props.servicePrincipals ?? [];
    const environment: Record<string, string> = {
      KANBUS_BACKEND: "s3",
      KANBUS_OBJECT_BUCKET: bucket.bucketName,
      KANBUS_CATALOG_TABLE: table.tableName,
    };
    if (servicePrincipals.length > 0) {
      environment.KANBUS_SERVICE_PRINCIPALS = Stack.of(this).toJsonString(
        servicePrincipals.map((principal) => ({
          role_arn: principal.role.roleArn,
          tenants: principal.tenants,
          provision: principal.provision ?? false,
          delegate_actor: principal.delegateActor ?? false,
        })),
      );
    }
    const kanbusFunction = new lambda.Function(this, "Function", {
      runtime: lambda.Runtime.PROVIDED_AL2023,
      architecture: lambda.Architecture.X86_64,
      handler: "bootstrap",
      code: resolveLambdaCode(props.lambda?.code),
      memorySize: props.lambda?.memorySize ?? DEFAULT_MEMORY_MEGABYTES,
      timeout: props.lambda?.timeout ?? Duration.seconds(DEFAULT_TIMEOUT_SECONDS),
      role: functionRole,
      logGroup,
      environment,
    });
    this.bucket = bucket;
    this.table = table;
    this.function = kanbusFunction;
    Tags.of(this).add("kanbus:environment", props.environmentName);

    if (props.users) {
      this.userApi = this.createApi(
        "UserApi",
        `kanbus-${props.environmentName}-users`,
        kanbusFunction,
        new authorizers.HttpJwtAuthorizer("UserAuthorizer", props.users.issuer, {
          jwtAudience: props.users.audiences,
        }),
      );
      this.userApiUrl = this.userApi.apiEndpoint;
    }
    if (servicePrincipals.length > 0) {
      this.serviceApi = this.createApi(
        "ServiceApi",
        `kanbus-${props.environmentName}-service`,
        kanbusFunction,
        new authorizers.HttpIamAuthorizer(),
      );
      this.serviceApiUrl = this.serviceApi.apiEndpoint;
      this.grantServiceInvoke(this.serviceApi, servicePrincipals);
    }
    if (props.createOutputs ?? true) {
      this.createOutputs(props.environmentName);
    }
  }

  private createBucket(removalPolicy: RemovalPolicy): s3.Bucket {
    return new s3.Bucket(this, "Bucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      removalPolicy,
    });
  }

  private createTable(removalPolicy: RemovalPolicy): dynamodb.Table {
    const table = new dynamodb.Table(this, "Table", {
      partitionKey: { name: "scope", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "path", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy,
    });
    for (const definition of INDEX_DEFINITIONS) {
      table.addGlobalSecondaryIndex({
        indexName: definition.indexName,
        partitionKey: { name: definition.partitionKeyName, type: dynamodb.AttributeType.STRING },
        sortKey: { name: "path", type: dynamodb.AttributeType.STRING },
        projectionType: dynamodb.ProjectionType.ALL,
      });
    }
    return table;
  }

  /**
   * The store keys objects as scope/path and _virtuus/scope/path, where scope is
   * tenant/project. A multi-tenant deployment cannot enumerate tenants at deploy
   * time, so object access covers the whole bucket, which this construct dedicates
   * to the service. The table is likewise granted whole, because DynamoDB
   * LeadingKeys conditions would need the tenant list. Tenant isolation is enforced
   * by the service from verified identity, and environments are isolated by
   * having separate buckets and tables.
   */
  private createFunctionRole(
    bucket: s3.Bucket,
    table: dynamodb.Table,
    logGroup: logs.LogGroup,
  ): iam.Role {
    const role = new iam.Role(this, "FunctionRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
    });
    role.addToPolicy(
      new iam.PolicyStatement({
        actions: ["logs:CreateLogStream", "logs:PutLogEvents"],
        resources: [logGroup.logGroupArn],
      }),
    );
    role.addToPolicy(
      new iam.PolicyStatement({
        actions: ["s3:ListBucket"],
        resources: [bucket.bucketArn],
      }),
    );
    role.addToPolicy(
      new iam.PolicyStatement({
        actions: ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
        resources: [bucket.arnForObjects("*")],
      }),
    );
    role.addToPolicy(
      new iam.PolicyStatement({
        actions: ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:Query"],
        resources: [
          table.tableArn,
          ...INDEX_DEFINITIONS.map((definition) => `${table.tableArn}/index/${definition.indexName}`),
        ],
      }),
    );
    return role;
  }

  private createApi(
    id: string,
    apiName: string,
    handler: lambda.IFunction,
    authorizer: apigatewayv2.IHttpRouteAuthorizer,
  ): apigatewayv2.HttpApi {
    const api = new apigatewayv2.HttpApi(this, id, { apiName });
    const integration = new integrations.HttpLambdaIntegration(`${id}Integration`, handler);
    for (const path of ROUTE_PATHS) {
      for (const method of ROUTE_METHODS) {
        new apigatewayv2.HttpRoute(api, `${method}${path.replace(/[^A-Za-z0-9]/g, "")}`, {
          httpApi: api,
          routeKey: apigatewayv2.HttpRouteKey.with(path, method),
          integration,
          authorizer,
        });
      }
    }
    return api;
  }

  private grantServiceInvoke(
    api: apigatewayv2.HttpApi,
    servicePrincipals: KanbusServicePrincipal[],
  ): void {
    const resources = ROUTE_PATHS.flatMap((path) =>
      ROUTE_METHODS.map((method) =>
        api.arnForExecuteApi(method, path.replace("{proxy+}", "*").replace(/\{[a-z]+\}/g, "*")),
      ),
    );
    servicePrincipals.forEach((principal, index) => {
      new iam.Policy(this, `ServiceInvokePolicy${index}`, {
        statements: [new iam.PolicyStatement({ actions: ["execute-api:Invoke"], resources })],
        roles: [principal.role],
      });
    });
  }

  private createOutputs(environmentName: string): void {
    if (this.userApiUrl) {
      new CfnOutput(this, "UserApiUrl", {
        value: this.userApiUrl,
        description: `Kanbus user API URL for ${environmentName}`,
      });
    }
    if (this.serviceApiUrl) {
      new CfnOutput(this, "ServiceApiUrl", {
        value: this.serviceApiUrl,
        description: `Kanbus service API URL for ${environmentName}`,
      });
    }
  }
}
