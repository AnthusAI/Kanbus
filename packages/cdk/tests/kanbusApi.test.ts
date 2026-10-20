import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { App, Duration, RemovalPolicy, Stack } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import * as events from "aws-cdk-lib/aws-events";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { KanbusApi, KanbusApiProps } from "../src";

const placeholderDirectory = mkdtempSync(join(tmpdir(), "kanbus-cdk-"));
const placeholderZipPath = join(placeholderDirectory, "kanbus-api-lambda.zip");
writeFileSync(placeholderZipPath, "placeholder");

type PartialProps = Omit<KanbusApiProps, "environmentName" | "lambda" | "archiveRetentionDays"> & {
  environmentName?: string;
  archiveRetentionDays?: number;
};

function placeholderCode(): lambda.Code {
  return lambda.Code.fromAsset(placeholderDirectory);
}

function buildStack(
  props: PartialProps,
  scope?: App,
): { stack: Stack; construct: KanbusApi; template: Template } {
  const stack = new Stack(scope ?? new App(), "TestStack");
  const construct = new KanbusApi(stack, "Kanbus", {
    environmentName: "development",
    archiveRetentionDays: 30,
    ...props,
    lambda: { code: placeholderCode(), sweeperCode: placeholderCode() },
  });
  return { stack, construct, template: Template.fromStack(stack) };
}

const userConfiguration = {
  issuer: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
  audiences: ["browser-client"],
};

function serviceRole(stack: Stack, id: string): iam.Role {
  return new iam.Role(stack, id, {
    assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
  });
}

function buildWithServiceRoles(
  entries: (role: iam.IRole[]) => KanbusApiProps["servicePrincipals"],
) {
  const app = new App();
  const stack = new Stack(app, "KanbusStack");
  const rolesStack = stack;
  const roles = [serviceRole(stack, "RoleOne"), serviceRole(stack, "RoleTwo")];
  const construct = new KanbusApi(stack, "Kanbus", {
    environmentName: "production",
    archiveRetentionDays: 30,
    servicePrincipals: entries(roles),
    lambda: { code: placeholderCode(), sweeperCode: placeholderCode() },
  });
  return { app, rolesStack, stack, construct, roles, template: Template.fromStack(stack) };
}

test("bucket is private, encrypted, TLS only, versioned and retained", () => {
  const { template } = buildStack({ users: userConfiguration });
  template.hasResourceProperties("AWS::S3::Bucket", {
    VersioningConfiguration: { Status: "Enabled" },
    PublicAccessBlockConfiguration: {
      BlockPublicAcls: true,
      BlockPublicPolicy: true,
      IgnorePublicAcls: true,
      RestrictPublicBuckets: true,
    },
    BucketEncryption: {
      ServerSideEncryptionConfiguration: [
        { ServerSideEncryptionByDefault: { SSEAlgorithm: "AES256" } },
      ],
    },
  });
  template.hasResource("AWS::S3::Bucket", {
    DeletionPolicy: "Retain",
    UpdateReplacePolicy: "Retain",
  });
  template.hasResourceProperties("AWS::S3::BucketPolicy", {
    PolicyDocument: {
      Statement: Match.arrayWith([
        Match.objectLike({
          Effect: "Deny",
          Action: "s3:*",
          Condition: { Bool: { "aws:SecureTransport": "false" } },
        }),
      ]),
    },
  });
});

test("table matches the contract with three global secondary indexes", () => {
  const { template } = buildStack({ users: userConfiguration });
  template.hasResourceProperties("AWS::DynamoDB::Table", {
    BillingMode: "PAY_PER_REQUEST",
    KeySchema: [
      { AttributeName: "scope", KeyType: "HASH" },
      { AttributeName: "path", KeyType: "RANGE" },
    ],
    PointInTimeRecoverySpecification: { PointInTimeRecoveryEnabled: true },
    GlobalSecondaryIndexes: [
      indexExpectation("by_type", "type_scope"),
      indexExpectation("by_status", "status_scope"),
      indexExpectation("by_type_status", "type_status_scope"),
    ],
  });
  template.hasResource("AWS::DynamoDB::Table", {
    DeletionPolicy: "Retain",
    UpdateReplacePolicy: "Retain",
  });
});

function indexExpectation(indexName: string, partitionKey: string) {
  return {
    IndexName: indexName,
    KeySchema: [
      { AttributeName: partitionKey, KeyType: "HASH" },
      { AttributeName: "path", KeyType: "RANGE" },
    ],
    Projection: { ProjectionType: "ALL" },
  };
}

test("removal policy can be overridden for both stateful resources", () => {
  const { template } = buildStack({
    users: userConfiguration,
    removalPolicy: RemovalPolicy.DESTROY,
  });
  template.hasResource("AWS::S3::Bucket", { DeletionPolicy: "Delete" });
  template.hasResource("AWS::DynamoDB::Table", { DeletionPolicy: "Delete" });
});

test("lambda runs the bundled bootstrap with the required environment", () => {
  const { template } = buildStack({ users: userConfiguration });
  template.hasResourceProperties("AWS::Lambda::Function", {
    Runtime: "provided.al2023",
    Handler: "bootstrap",
    Architectures: ["x86_64"],
    FunctionName: Match.absent(),
    MemorySize: 512,
    Timeout: 15,
    Environment: {
      Variables: {
        KANBUS_BACKEND: "s3",
        KANBUS_OBJECT_BUCKET: Match.anyValue(),
        KANBUS_CATALOG_TABLE: Match.anyValue(),
        KANBUS_ARCHIVE_RETENTION_DAYS: "30",
      },
    },
  });
  template.hasResourceProperties("AWS::Logs::LogGroup", { RetentionInDays: 90 });
});

test("lambda settings are bounded and overridable", () => {
  const stack = new Stack(new App(), "Bounded");
  new KanbusApi(stack, "Kanbus", {
    environmentName: "staging",
    archiveRetentionDays: 30,
    users: userConfiguration,
    lambda: {
      code: placeholderCode(),
      sweeperCode: placeholderCode(),
      memorySize: 1024,
      timeout: Duration.seconds(25),
    },
  });
  Template.fromStack(stack).hasResourceProperties("AWS::Lambda::Function", {
    MemorySize: 1024,
    Timeout: 25,
  });
  for (const invalid of [{ memorySize: 64 }, { timeout: Duration.seconds(31) }]) {
    assert.throws(
      () =>
        new KanbusApi(new Stack(new App(), "Invalid"), "Kanbus", {
          environmentName: "staging",
          archiveRetentionDays: 30,
          users: userConfiguration,
          lambda: { code: placeholderCode(), ...invalid },
        }),
      /lambda\./,
    );
  }
});

test("lambda role has least privilege on the bucket, table and log group", () => {
  const { template } = buildStack({ users: userConfiguration });
  template.resourceCountIs("AWS::IAM::Role", 2);
  template.hasResourceProperties("AWS::IAM::Role", {
    ManagedPolicyArns: Match.absent(),
  });
  const policies = template.findResources("AWS::IAM::Policy");
  const apiPolicies = Object.entries(policies).filter(([logicalId]) =>
    logicalId.startsWith("KanbusFunctionRole"),
  );
  assert.equal(apiPolicies.length, 1);
  const statements = apiPolicies.flatMap(
    ([, policy]) => (policy as any).Properties.PolicyDocument.Statement,
  );
  const actionsOf = (statement: any): string[] =>
    [].concat(statement.Action as never);
  const allActions = statements.flatMap(actionsOf).sort();
  assert.deepEqual(allActions, [
    "dynamodb:DeleteItem",
    "dynamodb:GetItem",
    "dynamodb:PutItem",
    "dynamodb:Query",
    "logs:CreateLogStream",
    "logs:PutLogEvents",
    "s3:DeleteObject",
    "s3:GetObject",
    "s3:ListBucket",
    "s3:PutObject",
  ]);
  for (const statement of statements) {
    assert.equal(statement.Effect, "Allow");
    assert.notEqual(JSON.stringify(statement.Resource), '"*"');
    assert.ok(!actionsOf(statement).some((action) => action.endsWith("*")));
  }
  const tableStatement = statements.find((statement: any) =>
    actionsOf(statement).includes("dynamodb:Query"),
  );
  assert.equal(tableStatement.Resource.length, 4);
  const objectStatement = statements.find((statement: any) =>
    actionsOf(statement).includes("s3:PutObject"),
  );
  assert.deepEqual(actionsOf(objectStatement).sort(), [
    "s3:DeleteObject",
    "s3:GetObject",
    "s3:PutObject",
  ]);
});

test("users only creates the JWT api with the contract routes", () => {
  const { construct, template } = buildStack({ users: userConfiguration });
  assert.ok(construct.userApi);
  assert.equal(construct.serviceApi, undefined);
  template.resourceCountIs("AWS::ApiGatewayV2::Api", 1);
  template.hasResourceProperties("AWS::ApiGatewayV2::Authorizer", {
    AuthorizerType: "JWT",
    JwtConfiguration: {
      Issuer: userConfiguration.issuer,
      Audience: userConfiguration.audiences,
    },
  });
  const routeKeys = Object.values(template.findResources("AWS::ApiGatewayV2::Route"))
    .map((route) => (route as any).Properties.RouteKey as string)
    .sort();
  assert.deepEqual(routeKeys, expectedRouteKeys());
  template.allResourcesProperties("AWS::ApiGatewayV2::Route", {
    AuthorizationType: "JWT",
  });
});

function expectedRouteKeys(): string[] {
  const methods = ["DELETE", "GET", "PATCH", "POST"];
  return [
    ...methods.map((method) => `${method} /{tenant}/{project}/api/{proxy+}`),
    ...methods.map((method) => `${method} /{tenant}/api/issues`),
  ].sort();
}

test("service principals create an AWS_IAM api and no user api", () => {
  const { construct, template } = buildWithServiceRoles((roles) => [
    { role: roles[0], tenants: "*" },
  ]);
  assert.equal(construct.userApi, undefined);
  assert.ok(construct.serviceApi);
  template.resourceCountIs("AWS::ApiGatewayV2::Api", 1);
  template.resourceCountIs("AWS::ApiGatewayV2::Authorizer", 0);
  template.allResourcesProperties("AWS::ApiGatewayV2::Route", {
    AuthorizationType: "AWS_IAM",
  });
  const routeKeys = Object.values(template.findResources("AWS::ApiGatewayV2::Route"))
    .map((route) => (route as any).Properties.RouteKey as string)
    .sort();
  assert.deepEqual(routeKeys, expectedRouteKeys());
});

test("only the given roles receive execute-api:Invoke on the service api", () => {
  const { stack, roles, template } = buildWithServiceRoles((all) => [
    { role: all[0], tenants: "*" },
  ]);
  const policies = Object.values(template.findResources("AWS::IAM::Policy")).filter((policy) =>
    JSON.stringify((policy as any).Properties.PolicyDocument).includes("execute-api:Invoke"),
  );
  assert.equal(policies.length, 1);
  const attached = (policies[0] as any).Properties.Roles;
  assert.equal(attached.length, 1);
  assert.deepEqual(attached, [stack.resolve(roles[0].roleName)]);
  assert.equal(JSON.stringify(attached).includes("RoleTwo"), false);
  for (const policy of policies) {
    for (const statement of (policy as any).Properties.PolicyDocument.Statement) {
      assert.equal(statement.Action, "execute-api:Invoke");
      assert.ok(JSON.stringify(statement.Resource).includes("ServiceApi"));
      assert.notEqual(JSON.stringify(statement.Resource), '"*"');
    }
  }
});

test("a role in another stack does not create a dependency cycle", () => {
  const app = new App();
  const rolesStack = new Stack(app, "RolesStack");
  const stack = new Stack(app, "KanbusStack");
  new KanbusApi(stack, "Kanbus", {
    environmentName: "production",
    archiveRetentionDays: 30,
    servicePrincipals: [{ role: serviceRole(rolesStack, "Role"), tenants: ["acme"] }],
    lambda: { code: placeholderCode(), sweeperCode: placeholderCode() },
  });
  const assembly = app.synth();
  assert.ok(assembly.getStackByName(stack.stackName));
  assert.ok(assembly.getStackByName(rolesStack.stackName));
});

test("KANBUS_SERVICE_PRINCIPALS renders wildcard and list tenants", () => {
  const { stack, template } = buildWithServiceRoles((roles) => [
    { role: roles[0], tenants: "*", provision: false, delegateActor: true },
    { role: roles[1], tenants: ["acme", "globex"] },
  ]);
  const functions = Object.values(template.findResources("AWS::Lambda::Function"));
  const variable = (functions[0] as any).Properties.Environment.Variables
    .KANBUS_SERVICE_PRINCIPALS;
  const pieces: unknown[] = stack.resolve(variable)["Fn::Join"][1];
  const rendered = pieces.map((piece) => (typeof piece === "string" ? piece : "ROLE_ARN")).join("");
  assert.deepEqual(JSON.parse(rendered), [
    { role_arn: "ROLE_ARN", tenants: "*", provision: false, delegate_actor: true },
    { role_arn: "ROLE_ARN", tenants: ["acme", "globex"], provision: false, delegate_actor: false },
  ]);
  assert.equal(pieces.filter((piece) => typeof piece !== "string").length, 2);
});

test("KANBUS_SERVICE_PRINCIPALS is absent when no service principals are given", () => {
  const { template } = buildStack({ users: userConfiguration });
  template.hasResourceProperties("AWS::Lambda::Function", {
    Environment: {
      Variables: { KANBUS_SERVICE_PRINCIPALS: Match.absent() },
    },
  });
});

test("lambda invoke permissions reference only the created apis", () => {
  const stack = new Stack(new App(), "BothApis");
  new KanbusApi(stack, "Kanbus", {
    environmentName: "development",
    archiveRetentionDays: 30,
    users: userConfiguration,
    servicePrincipals: [{ role: serviceRole(stack, "Caller"), tenants: "*" }],
    lambda: { code: placeholderCode(), sweeperCode: placeholderCode() },
  });
  const template = Template.fromStack(stack);
  const permissions = Object.values(template.findResources("AWS::Lambda::Permission")).filter(
    (permission) => (permission as any).Properties.Principal === "apigateway.amazonaws.com",
  );
  assert.equal(permissions.length, 16);
  const apiLogicalIds = Object.keys(template.findResources("AWS::ApiGatewayV2::Api"));
  assert.equal(apiLogicalIds.length, 2);
  for (const permission of permissions) {
    const properties = (permission as any).Properties;
    assert.equal(properties.Action, "lambda:InvokeFunction");
    assert.equal(properties.Principal, "apigateway.amazonaws.com");
    const referencedApis = apiLogicalIds.filter((logicalId) =>
      JSON.stringify(properties.SourceArn).includes(logicalId),
    );
    assert.equal(referencedApis.length, 1);
  }
  const otherInvocations = Object.values(template.findResources("AWS::IAM::Policy")).filter(
    (policy) => JSON.stringify(policy).includes("lambda:InvokeFunction"),
  );
  assert.equal(otherInvocations.length, 0);
});

test("physical names are generated or environment qualified and distinct", () => {
  const app = new App();
  const stack = new Stack(app, "Shared");
  for (const environmentName of ["staging", "production"]) {
    const role = serviceRole(stack, `Role-${environmentName}`);
    new KanbusApi(stack, `Kanbus-${environmentName}`, {
      environmentName,
      archiveRetentionDays: 30,
      users: userConfiguration,
      servicePrincipals: [{ role, tenants: "*" }],
      lambda: { code: placeholderCode(), sweeperCode: placeholderCode() },
    });
  }
  const template = Template.fromStack(stack);
  template.allResourcesProperties("AWS::DynamoDB::Table", { TableName: Match.absent() });
  template.allResourcesProperties("AWS::Lambda::Function", { FunctionName: Match.absent() });
  template.allResourcesProperties("AWS::S3::Bucket", { BucketName: Match.absent() });
  const apiNames = Object.values(template.findResources("AWS::ApiGatewayV2::Api"))
    .map((api) => (api as any).Properties.Name as string)
    .sort();
  assert.deepEqual(apiNames, [
    "kanbus-production-service",
    "kanbus-production-users",
    "kanbus-staging-service",
    "kanbus-staging-users",
  ]);
  assert.equal(new Set(apiNames).size, apiNames.length);
});

test("construct inside an existing stack with caller lambda and role synthesizes", () => {
  const app = new App();
  const stack = new Stack(app, "ChatticusProduction");
  const callerRole = new iam.Role(stack, "CallerRole", {
    assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  });
  const kanbus = new KanbusApi(stack, "Kanbus", {
    environmentName: "production",
    archiveRetentionDays: 30,
    servicePrincipals: [{ role: callerRole, tenants: "*", delegateActor: true }],
    lambda: { code: placeholderCode(), sweeperCode: placeholderCode() },
  });
  new lambda.Function(stack, "Caller", {
    runtime: lambda.Runtime.NODEJS_20_X,
    handler: "index.handler",
    code: lambda.Code.fromInline("exports.handler = async () => ({});"),
    role: callerRole,
    environment: { KANBUS_SERVICE_API_URL: kanbus.serviceApiUrl as string },
  });
  const assembly = app.synth();
  const template = Template.fromStack(stack);
  const caller = Object.values(template.findResources("AWS::Lambda::Function")).find(
    (candidate) => JSON.stringify(candidate).includes("KANBUS_SERVICE_API_URL"),
  ) as any;
  assert.ok(caller.Properties.Environment.Variables.KANBUS_SERVICE_API_URL);
  assert.equal(assembly.stacks.length, 1);
  const json = template.toJSON();
  assert.equal(JSON.stringify(json).includes("Fn::ImportValue"), false);
  assert.equal(JSON.stringify(json).includes("AWS::CloudFormation::Stack"), false);
  for (const output of Object.values(json.Outputs ?? {})) {
    assert.equal((output as any).Export, undefined);
  }
});

test("outputs can be disabled", () => {
  const { template } = buildStack({ users: userConfiguration, createOutputs: false });
  assert.equal(template.toJSON().Outputs, undefined);
});

test("exposes resources, endpoints and outputs", () => {
  const { construct, template } = buildWithServiceRoles((roles) => [
    { role: roles[0], tenants: "*" },
  ]);
  assert.ok(construct.bucket);
  assert.ok(construct.table);
  assert.ok(construct.function);
  assert.ok(construct.serviceApiUrl);
  assert.equal(construct.userApiUrl, undefined);
  const outputs = template.toJSON().Outputs;
  const outputKeys = Object.keys(outputs);
  assert.equal(outputKeys.length, 1);
  assert.match(outputKeys[0], /^KanbusServiceApiUrl/);
  assert.match(outputs[outputKeys[0]].Description, /production/);
});

test("omitting both users and servicePrincipals throws", () => {
  assert.throws(
    () =>
      new KanbusApi(new Stack(new App(), "Empty"), "Kanbus", {
        environmentName: "development",
        archiveRetentionDays: 30,
        lambda: { code: placeholderCode(), sweeperCode: placeholderCode() },
      }),
    /at least one of users or servicePrincipals/,
  );
  assert.throws(
    () =>
      new KanbusApi(new Stack(new App(), "EmptyList"), "Kanbus", {
        environmentName: "development",
        archiveRetentionDays: 30,
        servicePrincipals: [],
        lambda: { code: placeholderCode(), sweeperCode: placeholderCode() },
      }),
    /at least one of users or servicePrincipals/,
  );
});

test("invalid environment names and tenants are rejected", () => {
  assert.throws(() => buildStack({ environmentName: "Prod_1", users: userConfiguration }), /environmentName/);
  const role = serviceRole(new Stack(new App(), "Roles"), "Role");
  assert.throws(
    () => buildStack({ servicePrincipals: [{ role, tenants: [] }] }),
    /tenants/,
  );
  assert.throws(
    () =>
      buildStack({
        servicePrincipals: [
          { role, tenants: "*" },
          { role, tenants: "*" },
        ],
      }),
    /only once/,
  );
});

test("the default bundled zip is required when no code override is given", () => {
  assert.throws(
    () =>
      new KanbusApi(new Stack(new App(), "NoZip"), "Kanbus", {
        environmentName: "development",
        archiveRetentionDays: 30,
        users: userConfiguration,
      }),
    /kanbus-api-lambda\.zip/,
  );
});

test("sweeper function runs the bundled bootstrap with the data environment and no service principals", () => {
  const stack = new Stack(new App(), "Sweeper");
  new KanbusApi(stack, "Kanbus", {
    environmentName: "development",
    archiveRetentionDays: 45,
    servicePrincipals: [{ role: serviceRole(stack, "Caller"), tenants: "*" }],
    lambda: { code: placeholderCode(), sweeperCode: placeholderCode() },
  });
  const template = Template.fromStack(stack);
  const functions = Object.values(template.findResources("AWS::Lambda::Function"));
  assert.equal(functions.length, 2);
  const sweeper = functions.find((candidate) =>
    JSON.stringify(candidate).includes("SweeperRole"),
  ) as any;
  assert.equal(sweeper.Properties.Runtime, "provided.al2023");
  assert.equal(sweeper.Properties.Handler, "bootstrap");
  assert.deepEqual(sweeper.Properties.Architectures, ["x86_64"]);
  assert.equal(sweeper.Properties.Timeout, 300);
  assert.equal(sweeper.Properties.ReservedConcurrentExecutions, 1);
  assert.deepEqual(Object.keys(sweeper.Properties.Environment.Variables).sort(), [
    "KANBUS_ARCHIVE_RETENTION_DAYS",
    "KANBUS_BACKEND",
    "KANBUS_CATALOG_TABLE",
    "KANBUS_OBJECT_BUCKET",
  ]);
  assert.equal(sweeper.Properties.Environment.Variables.KANBUS_BACKEND, "s3");
  assert.equal(sweeper.Properties.Environment.Variables.KANBUS_ARCHIVE_RETENTION_DAYS, "45");
  template.hasResourceProperties("AWS::Lambda::Function", {
    ReservedConcurrentExecutions: Match.absent(),
    Environment: { Variables: { KANBUS_ARCHIVE_RETENTION_DAYS: "45" } },
  });
  template.resourceCountIs("AWS::Logs::LogGroup", 2);
});

test("sweeper role has the same data grants as the api role and nothing else", () => {
  const { template } = buildStack({ users: userConfiguration });
  const policies = Object.entries(template.findResources("AWS::IAM::Policy"));
  const statementsFor = (prefix: string) =>
    policies
      .filter(([logicalId]) => logicalId.startsWith(prefix))
      .flatMap(([, policy]) => (policy as any).Properties.PolicyDocument.Statement);
  const sweeperStatements = statementsFor("KanbusSweeperRole");
  const apiStatements = statementsFor("KanbusFunctionRole");
  const actionsOf = (statements: any[]): string[] =>
    statements.flatMap((statement) => [].concat(statement.Action as never) as string[]).sort();
  assert.deepEqual(actionsOf(sweeperStatements), actionsOf(apiStatements));
  assert.ok(actionsOf(sweeperStatements).includes("s3:DeleteObject"));
  assert.ok(actionsOf(sweeperStatements).includes("dynamodb:DeleteItem"));
  for (const statement of sweeperStatements) {
    assert.notEqual(JSON.stringify(statement.Resource), '"*"');
  }
});

test("an hourly schedule rule targets only the sweeper and no one else can invoke it", () => {
  const { template, construct } = buildStack({ users: userConfiguration });
  template.resourceCountIs("AWS::Events::Rule", 1);
  template.hasResourceProperties("AWS::Events::Rule", {
    ScheduleExpression: "rate(1 hour)",
    State: "ENABLED",
    Targets: [Match.objectLike({ Arn: Match.anyValue() })],
  });
  const rule = Object.values(template.findResources("AWS::Events::Rule"))[0] as any;
  assert.equal(rule.Properties.Targets.length, 1);
  assert.ok(JSON.stringify(rule.Properties.Targets[0].Arn).includes("Sweeper"));
  const sweeperPermissions = Object.values(template.findResources("AWS::Lambda::Permission")).filter(
    (permission) => JSON.stringify((permission as any).Properties.FunctionName).includes("Sweeper"),
  );
  assert.equal(sweeperPermissions.length, 1);
  assert.equal((sweeperPermissions[0] as any).Properties.Principal, "events.amazonaws.com");
  assert.ok(construct.sweeperFunction);
});

test("sweepSchedule overrides the default schedule", () => {
  const { template } = buildStack({
    users: userConfiguration,
    sweepSchedule: events.Schedule.rate(Duration.minutes(15)),
  });
  template.hasResourceProperties("AWS::Events::Rule", {
    ScheduleExpression: "rate(15 minutes)",
  });
});

test("archiveRetentionDays must be a positive integer", () => {
  for (const invalid of [0, -1, 1.5, Number.NaN, undefined]) {
    assert.throws(
      () => buildStack({ users: userConfiguration, archiveRetentionDays: invalid as never }),
      /archiveRetentionDays/,
    );
  }
});

test("the bundled sweeper zip is required when no sweeper code override is given", () => {
  assert.throws(
    () =>
      new KanbusApi(new Stack(new App(), "NoSweeperZip"), "Kanbus", {
        environmentName: "development",
        archiveRetentionDays: 30,
        users: userConfiguration,
        lambda: { code: placeholderCode() },
      }),
    /kanbus-api-sweeper\.zip/,
  );
});
