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
import { createKanbusApiClient } from "../../api-client/src/client";

interface RecordedCall {
  method: string;
  path: string;
}

const placeholderDirectory = mkdtempSync(join(tmpdir(), "kanbus-cdk-contract-"));
writeFileSync(join(placeholderDirectory, "kanbus-api-lambda.zip"), "placeholder");

function synthesizeTemplate(): Template {
  const stack = new Stack(new App(), "ContractStack");
  const serviceRole = new iam.Role(stack, "ServiceRole", {
    assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
  });
  new KanbusApi(stack, "Kanbus", {
    environmentName: "development",
    archiveRetentionDays: 30,
    users: { issuer: "https://issuer.example.com", audiences: ["audience"] },
    servicePrincipals: [{ role: serviceRole, tenants: "*" }],
    lambda: {
      code: lambda.Code.fromAsset(placeholderDirectory),
      sweeperCode: lambda.Code.fromAsset(placeholderDirectory),
    },
  });
  return Template.fromStack(stack);
}

async function recordEveryClientCall(): Promise<RecordedCall[]> {
  const calls: RecordedCall[] = [];
  const client = createKanbusApiClient({
    baseUrl: "https://api.example.com",
    fetch: async (input, init) => {
      calls.push({ method: String(init?.method), path: new URL(input).pathname });
      return new Response("{}", { status: 200 });
    },
  });
  const board = client.board("acme", "web");
  const write = { operationId: "operation-1", actor: "tester" } as never;
  const revisionWrite = { operationId: "operation-1", actor: "tester", ifMatch: "1" } as never;
  await board.getConfig();
  await board.provision({ operationId: "operation-1" } as never);
  await board.listIssues();
  await board.getIssue("issue-1");
  await board.createIssue({ title: "title" } as never, write);
  await board.updateIssue("issue-1", {} as never, revisionWrite);
  await board.deleteIssue("issue-1", revisionWrite);
  await board.addComment("issue-1", "text", revisionWrite);
  await board.getEvents("issue-1");
  await board.archive(write);
  await board.restore(write);
  await board.purge(write);
  await client.listAcrossBoards("acme", ["web", "api"]);
  return calls;
}

function patternFromTemplatePath(templatePath: string): RegExp {
  const source = templatePath
    .split("/")
    .map((part) => (part === "{proxy+}" ? ".+" : part.startsWith("{") ? "[^/]+" : part))
    .join("/");
  return new RegExp(`^${source}$`);
}

function routeKeysOfAllApis(template: Template): string[] {
  const routes = template.findResources("AWS::ApiGatewayV2::Route");
  return Object.values(routes).map((route) => String(route.Properties.RouteKey));
}

function matchesRouteKey(call: RecordedCall, routeKey: string): boolean {
  const [method, templatePath] = routeKey.split(" ");
  return method === call.method && patternFromTemplatePath(templatePath).test(call.path);
}

function invokeResourceSuffixes(template: Template): string[] {
  const policies = template.findResources("AWS::IAM::Policy");
  const suffixes: string[] = [];
  for (const policy of Object.values(policies)) {
    for (const statement of policy.Properties.PolicyDocument.Statement) {
      if (statement.Action !== "execute-api:Invoke") continue;
      for (const resource of statement.Resource) {
        const joined = JSON.stringify(resource);
        const stage = joined.match(/\/\*\\"?,?\\?"?\/?([A-Z]+\/[^"\\]*)/);
        const tail = [...joined.matchAll(/"\/\*\/([A-Z]+)(\/[^"]*)"/g)].pop();
        if (tail) suffixes.push(`${tail[1]} ${tail[2]}`);
        else if (stage) suffixes.push(stage[1].replace("/", " /"));
      }
    }
  }
  return suffixes;
}

test("every client call matches a route on both APIs", async () => {
  const template = synthesizeTemplate();
  const calls = await recordEveryClientCall();
  assert.ok(calls.length >= 13);
  const routeKeys = routeKeysOfAllApis(template);
  for (const call of calls) {
    const matching = routeKeys.filter((routeKey) => matchesRouteKey(call, routeKey));
    assert.equal(
      matching.length,
      2,
      `${call.method} ${call.path} must be routed on the user API and the service API`,
    );
  }
});

test("service invoke policy covers every client call", async () => {
  const template = synthesizeTemplate();
  const calls = await recordEveryClientCall();
  const suffixes = invokeResourceSuffixes(template);
  assert.ok(suffixes.length > 0);
  for (const call of calls) {
    const covered = suffixes.some((suffix) => {
      const [method, templatePath] = suffix.split(" ");
      const pattern = new RegExp(`^${templatePath.replace(/\*/g, "[^/]+").replace(/\[\^\/\]\+$/, ".+")}$`);
      return method === call.method && pattern.test(call.path);
    });
    assert.ok(covered, `${call.method} ${call.path} is not covered by the invoke policy`);
  }
});
