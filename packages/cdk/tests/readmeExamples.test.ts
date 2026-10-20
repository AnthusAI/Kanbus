import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { App, Stack } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import { KanbusApi } from "../src";

const placeholderDirectory = mkdtempSync(join(tmpdir(), "kanbus-cdk-readme-"));
writeFileSync(join(placeholderDirectory, "kanbus-api-lambda.zip"), "placeholder");
const code = () => lambda.Code.fromAsset(placeholderDirectory);

test("Chatticus example: three environments, two service roles, no user api", () => {
  const app = new App();
  const applicationStack = new Stack(app, "ChatticusApplication");
  const controlPlaneRole = new iam.Role(applicationStack, "ControlPlaneRole", {
    assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
  });
  const reporterRole = new iam.Role(applicationStack, "ReporterRole", {
    assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
  });
  const stacks = ["development", "staging", "production"].map((environmentName) => {
    const stack = new Stack(app, `Kanbus-${environmentName}`);
    new KanbusApi(stack, "Kanbus", {
      environmentName,
      archiveRetentionDays: 30,
      servicePrincipals: [
        { role: controlPlaneRole, tenants: "*", provision: true, delegateActor: true },
        { role: reporterRole, tenants: ["chatticus"] },
      ],
      lambda: { code: code(), sweeperCode: code() },
    });
    return stack;
  });
  const assembly = app.synth();
  assert.equal(stacks.length, 3);
  for (const stack of stacks) {
    assert.ok(assembly.getStackByName(stack.stackName));
    const template = Template.fromStack(stack);
    template.resourceCountIs("AWS::ApiGatewayV2::Api", 1);
    template.resourceCountIs("AWS::ApiGatewayV2::Authorizer", 0);
  }
});

test("Prospectus example: one board with users only", () => {
  const stack = new Stack(new App(), "ProspectusBackend");
  const kanbus = new KanbusApi(stack, "Kanbus", {
    environmentName: "production",
    archiveRetentionDays: 30,
    users: {
      issuer: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
      audiences: ["prospectus-browser-client"],
    },
    lambda: { code: code(), sweeperCode: code() },
  });
  const template = Template.fromStack(stack);
  template.resourceCountIs("AWS::ApiGatewayV2::Api", 1);
  template.resourceCountIs("AWS::ApiGatewayV2::Authorizer", 1);
  assert.ok(kanbus.userApiUrl);
  assert.equal(kanbus.serviceApi, undefined);
});
