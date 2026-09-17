"""Synthesized contract tests for the direct DynamoDB mutex lease API."""

import unittest

from aws_cdk import App
from aws_cdk.assertions import Template

from kanbus_cloud.cloud_stack import KanbusCloudFoundationStack


class CoordinationMutexApiTemplateTests(unittest.TestCase):
    """Keep lease routes, auth, storage, and IAM aligned with both clients."""

    @staticmethod
    def _template() -> Template:
        app = App(context={"env_name": "test"})
        stack = KanbusCloudFoundationStack(
            app, "KanbusCloudFoundationMutexTest", env_name="test"
        )
        return Template.from_stack(stack)

    @staticmethod
    def _routes(resources: dict) -> dict[tuple[str, str], dict]:
        paths: dict[str, str] = {}
        unresolved = {
            logical_id: resource
            for logical_id, resource in resources.items()
            if resource["Type"] == "AWS::ApiGateway::Resource"
        }
        while unresolved:
            progress = False
            for logical_id, resource in list(unresolved.items()):
                properties = resource["Properties"]
                parent = properties["ParentId"]
                if "Fn::GetAtt" in parent:
                    parent_path = ""
                elif parent.get("Ref") in paths:
                    parent_path = paths[parent["Ref"]]
                else:
                    continue
                paths[logical_id] = f"{parent_path}/{properties['PathPart']}"
                del unresolved[logical_id]
                progress = True
            if not progress:
                raise AssertionError(f"Unresolved API resource parents: {unresolved}")

        routes = {}
        for resource in resources.values():
            if resource["Type"] != "AWS::ApiGateway::Method":
                continue
            properties = resource["Properties"]
            route = paths.get(properties["ResourceId"].get("Ref"), "")
            routes[(properties["HttpMethod"], route)] = properties
        return routes

    @staticmethod
    def _joined(value) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and "Fn::Join" in value:
            return "".join(
                part if isinstance(part, str) else "<TOKEN>"
                for part in value["Fn::Join"][1]
            )
        return str(value)

    def test_lease_table_uses_server_expiration_as_ttl(self) -> None:
        resources = self._template().to_json()["Resources"]
        tables = [
            resource["Properties"]
            for resource in resources.values()
            if resource["Type"] == "AWS::DynamoDB::Table"
            and resource["Properties"].get("TableName")
            == "kanbus-coordination-leases-test"
        ]
        self.assertEqual(len(tables), 1)
        properties = tables[0]
        self.assertEqual(
            properties["TimeToLiveSpecification"],
            {"AttributeName": "expires_at", "Enabled": True},
        )
        self.assertEqual(properties["BillingMode"], "PAY_PER_REQUEST")
        self.assertEqual(
            properties["KeySchema"],
            [
                {"AttributeName": "tenant_key", "KeyType": "HASH"},
                {"AttributeName": "resource_key", "KeyType": "RANGE"},
            ],
        )

    def test_routes_use_direct_dynamodb_integrations_and_cognito(self) -> None:
        resources = self._template().to_json()["Resources"]
        routes = self._routes(resources)
        expected = {
            ("POST", "/api/coordination/leases/{resource}"): "UpdateItem",
            ("PUT", "/api/coordination/leases/{resource}"): "UpdateItem",
            ("DELETE", "/api/coordination/leases/{resource}"): "DeleteItem",
            ("GET", "/api/coordination/leases/{resource}"): "GetItem",
        }
        for route, action in expected.items():
            with self.subTest(route=route):
                method = routes[route]
                self.assertEqual(method["AuthorizationType"], "COGNITO_USER_POOLS")
                self.assertIn("AuthorizerId", method)
                integration = method["Integration"]
                self.assertEqual(integration["Type"], "AWS")
                self.assertEqual(integration["IntegrationHttpMethod"], "POST")
                self.assertIn(
                    f"dynamodb:action/{action}", self._joined(integration["Uri"])
                )
                self.assertIn("Credentials", integration)
                self.assertEqual(
                    integration["RequestParameters"][
                        "integration.request.header.Content-Type"
                    ],
                    "'application/x-amz-json-1.0'",
                )

        user_pool = next(
            resource["Properties"]
            for resource in resources.values()
            if resource["Type"] == "AWS::Cognito::UserPool"
        )
        schema_names = [attribute["Name"] for attribute in user_pool["Schema"]]
        self.assertIn("account", schema_names)
        self.assertIn("project", schema_names)

    def test_acquire_requires_and_persists_router_revision_verbatim(self) -> None:
        resources = self._template().to_json()["Resources"]
        acquire = self._routes(resources)[
            ("POST", "/api/coordination/leases/{resource}")
        ]
        model_id = acquire["RequestModels"]["application/json"]["Ref"]
        schema = resources[model_id]["Properties"]["Schema"]
        self.assertEqual(
            schema["required"], ["owner", "claim_id", "revision", "ttl_seconds"]
        )
        request = self._joined(
            acquire["Integration"]["RequestTemplates"]["application/json"]
        )
        self.assertIn('":revision":{"N":"$input.path(\'$.revision\')"}', request)
        self.assertIn("#revision = :revision", request)
        self.assertNotIn("#revision = #revision +", request)
        self.assertIn("$context.requestTimeEpoch / 1000", request)
        self.assertIn('":expires_at":{"N":"$expiresAt"}', request)
        self.assertIn("attribute_not_exists(#owner) OR #expires_at <= :now", request)

        conflict = acquire["Integration"]["IntegrationResponses"][0]
        self.assertEqual(conflict["StatusCode"], "409")
        self.assertIn(
            '"error":"lease already held"',
            conflict["ResponseTemplates"]["application/json"],
        )
        self.assertIn(
            "201", [response["StatusCode"] for response in acquire["MethodResponses"]]
        )
        acquire_success = acquire["Integration"]["IntegrationResponses"][-1][
            "ResponseTemplates"
        ]["application/json"]
        for field in [
            "resource",
            "owner",
            "claim_id",
            "revision",
            "claimed_at",
            "expires_at",
        ]:
            self.assertIn(f'"{field}"', acquire_success)

    def test_renew_release_and_inspect_distinguish_expiry_and_owner_mismatch(
        self,
    ) -> None:
        routes = self._routes(self._template().to_json()["Resources"])
        renew = routes[("PUT", "/api/coordination/leases/{resource}")]
        renew_request = self._joined(
            renew["Integration"]["RequestTemplates"]["application/json"]
        )
        self.assertIn(
            "#owner = :owner AND #claim_id = :claim_id AND #expires_at > :now",
            renew_request,
        )
        self.assertIn("#expires_at = #expires_at + :extension", renew_request)
        self.assertNotIn("#revision =", renew_request)
        self.assertIn("ReturnValuesOnConditionCheckFailure", renew_request)
        renew_error = renew["Integration"]["IntegrationResponses"][0]
        self.assertEqual(renew_error["StatusCode"], "403")
        renew_error_template = renew_error["ResponseTemplates"]["application/json"]
        self.assertIn("responseOverride.status = 404", renew_error_template)
        self.assertIn("responseOverride.status = 403", renew_error_template)

        release = routes[("DELETE", "/api/coordination/leases/{resource}")]
        release_request = self._joined(
            release["Integration"]["RequestTemplates"]["application/json"]
        )
        self.assertIn(
            "#owner = :owner AND #claim_id = :claim_id AND #expires_at > :now",
            release_request,
        )
        self.assertEqual(
            [
                response["StatusCode"]
                for response in release["Integration"]["IntegrationResponses"]
            ],
            ["403", "204"],
        )

        inspect = routes[("GET", "/api/coordination/leases/{resource}")]
        inspect_request = self._joined(
            inspect["Integration"]["RequestTemplates"]["application/json"]
        )
        self.assertIn('"ConsistentRead":true', inspect_request)
        inspect_template = inspect["Integration"]["IntegrationResponses"][-1][
            "ResponseTemplates"
        ]["application/json"]
        inspect_statuses = [
            response["StatusCode"] for response in inspect["MethodResponses"]
        ]
        self.assertIn("200", inspect_statuses)
        self.assertIn("404", inspect_statuses)
        self.assertIn("responseOverride.status = 404", inspect_template)
        self.assertIn('"error":"no live lease"', inspect_template)
        self.assertIn("$util.parseJson($item.expires_at.N)", inspect_template)
        self.assertIn("$expiresAt <= $now", inspect_template)

    def test_tenant_scope_is_claim_derived_and_service_role_is_table_scoped(
        self,
    ) -> None:
        resources = self._template().to_json()["Resources"]
        routes = self._routes(resources)
        lease_route = "/api/coordination/leases/{resource}"
        lease_methods = [
            properties
            for (method, path), properties in routes.items()
            if path == lease_route and method in {"GET", "POST", "PUT", "DELETE"}
        ]
        self.assertEqual(len(lease_methods), 4)
        for method in lease_methods:
            request = self._joined(
                method["Integration"]["RequestTemplates"]["application/json"]
            )
            self.assertIn("custom:account", request)
            self.assertIn("custom:project", request)
            self.assertIn("base64Encode($account)", request)
            self.assertIn("base64Encode($project)", request)
            self.assertIn("$input.params('resource')", request)
            self.assertNotIn("$.tenant", request)

        table_id = next(
            logical_id
            for logical_id, resource in resources.items()
            if resource["Type"] == "AWS::DynamoDB::Table"
            and resource["Properties"].get("TableName")
            == "kanbus-coordination-leases-test"
        )
        statements = [
            statement
            for policy in resources.values()
            if policy["Type"] == "AWS::IAM::Policy"
            for statement in policy["Properties"]["PolicyDocument"]["Statement"]
        ]
        lease_statement = next(
            statement
            for statement in statements
            if table_id in str(statement.get("Resource", []))
            and "dynamodb:UpdateItem" in str(statement.get("Action", []))
        )
        self.assertEqual(
            set(lease_statement["Action"]),
            {"dynamodb:DeleteItem", "dynamodb:GetItem", "dynamodb:UpdateItem"},
        )
        self.assertNotIn("*", str(lease_statement["Resource"]))


if __name__ == "__main__":
    unittest.main()
