"""Synthesis contract tests for the disposable remote coordination stack."""

import unittest

from aws_cdk import App
from aws_cdk.assertions import Template

from kanbus_cloud.coordination_stack import (
    KanbusCoordinationIntegrationStack,
    KanbusCoordinationProductionStack,
)


class CoordinationIntegrationStackTests(unittest.TestCase):
    @staticmethod
    def _template() -> Template:
        app = App()
        stack = KanbusCoordinationIntegrationStack(
            app, "KanbusCoordinationIntegrationTest", env_name="coordination-it"
        )
        return Template.from_stack(stack)

    @staticmethod
    def _production_template() -> Template:
        app = App()
        stack = KanbusCoordinationProductionStack(
            app,
            "KanbusCoordinationProductionTest",
            env_name="prod",
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
            path = paths[properties["ResourceId"].get("Ref")]
            routes[(properties["HttpMethod"], path)] = properties
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

    def test_stack_is_disposable_and_contains_only_coordination_resources(self) -> None:
        rendered = self._template().to_json()
        resources = rendered["Resources"]
        types = [resource["Type"] for resource in resources.values()]
        for forbidden in (
            "AWS::EC2::VPC",
            "AWS::EC2::Subnet",
            "AWS::EFS::FileSystem",
            "AWS::S3::Bucket",
            "AWS::SQS::Queue",
        ):
            self.assertNotIn(forbidden, types)

        self.assertEqual(types.count("AWS::DynamoDB::Table"), 2)
        self.assertEqual(types.count("AWS::IoT::Authorizer"), 1)
        self.assertEqual(types.count("AWS::SecretsManager::Secret"), 1)
        for item in resources.values():
            if item["Type"] in (
                "AWS::Cognito::UserPool",
                "AWS::IoT::Authorizer",
                "AWS::SecretsManager::Secret",
            ):
                self.assertEqual(item.get("DeletionPolicy", "Delete"), "Delete")
        tables = [
            item
            for item in resources.values()
            if item["Type"] == "AWS::DynamoDB::Table"
        ]
        for table in tables:
            self.assertEqual(table["DeletionPolicy"], "Delete")
            self.assertEqual(table["UpdateReplacePolicy"], "Delete")
            self.assertEqual(table["Properties"]["BillingMode"], "PAY_PER_REQUEST")

        user_pool = next(
            item["Properties"]
            for item in resources.values()
            if item["Type"] == "AWS::Cognito::UserPool"
        )
        attributes = {item["Name"]: item for item in user_pool["Schema"]}
        self.assertFalse(attributes["account"]["Mutable"])
        self.assertFalse(attributes["project"]["Mutable"])
        self.assertEqual(
            resources[
                next(
                    logical_id
                    for logical_id, item in resources.items()
                    if item["Type"] == "AWS::Cognito::UserPool"
                )
            ]["DeletionPolicy"],
            "Delete",
        )

    def test_api_outputs_and_token_lifecycle_are_wired(self) -> None:
        rendered = self._template().to_json()
        resources = rendered["Resources"]
        outputs = rendered["Outputs"]
        self.assertIn("CoordinationLeaseApiBaseUrl", outputs)
        base_url = self._joined(outputs["CoordinationLeaseApiBaseUrl"]["Value"])
        self.assertNotIn("/api/coordination/leases", base_url)
        base_parts = outputs["CoordinationLeaseApiBaseUrl"]["Value"]["Fn::Join"][1]
        stage_ref = base_parts[-2]["Ref"]
        self.assertEqual(
            resources[stage_ref]["Properties"]["StageName"], "coordination-it"
        )
        self.assertEqual(base_parts[-1], "/")
        for output in (
            "UserPoolId",
            "UserPoolClientId",
            "IotDataEndpointAddress",
            "MqttTokenAuthorizerName",
        ):
            self.assertIn(output, outputs)

        routes = self._routes(resources)
        self.assertIn(("GET", "/api/tokens"), routes)
        self.assertIn(("POST", "/api/tokens"), routes)
        self.assertIn(("POST", "/api/tokens/{token_id}/revoke"), routes)
        for key in (
            ("GET", "/api/tokens"),
            ("POST", "/api/tokens"),
            ("POST", "/api/tokens/{token_id}/revoke"),
        ):
            self.assertEqual(routes[key]["AuthorizationType"], "COGNITO_USER_POOLS")

        token_admin_lambdas = [
            item["Properties"]
            for item in resources.values()
            if item["Type"] == "AWS::Lambda::Function"
            and item["Properties"].get("Handler") == "token_admin.handler"
        ]
        authorizer_lambdas = [
            item["Properties"]
            for item in resources.values()
            if item["Type"] == "AWS::Lambda::Function"
            and item["Properties"].get("Handler") == "mqtt_authorizer.handler"
        ]
        self.assertEqual(len(token_admin_lambdas), 1)
        self.assertEqual(len(authorizer_lambdas), 1)

    def test_lease_routes_preserve_direct_dynamodb_contract_and_error_mapping(
        self,
    ) -> None:
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
                integration = method["Integration"]
                self.assertEqual(integration["Type"], "AWS")
                self.assertIn(
                    f"dynamodb:action/{action}", self._joined(integration["Uri"])
                )
                request = self._joined(
                    integration["RequestTemplates"]["application/json"]
                )
                self.assertIn('"InvalidTenantScope":true', request)
                self.assertIn("$account == ''", request)
                self.assertIn("$project == ''", request)
                self.assertIn("$util.urlDecode($input.params('resource'))", request)
                errors = integration["IntegrationResponses"][0]
                error_template = errors["ResponseTemplates"]["application/json"]
                self.assertIn('"error":"tenant scope missing"', error_template)
                self.assertIn("= 403", error_template)
                self.assertEqual(errors["SelectionPattern"], "4\\d{2}")
                self.assertIn(
                    "403",
                    [response["StatusCode"] for response in method["MethodResponses"]],
                )

        acquire = routes[("POST", "/api/coordination/leases/{resource}")]
        acquire_request = self._joined(
            acquire["Integration"]["RequestTemplates"]["application/json"]
        )
        self.assertIn(
            '"ConditionExpression":"attribute_not_exists(#owner) OR #expires_at <= :now"',
            acquire_request,
        )
        self.assertIn(
            '":revision":{"N":"$input.path(\'$.revision\')"}', acquire_request
        )
        acquire_error = acquire["Integration"]["IntegrationResponses"][0][
            "ResponseTemplates"
        ]["application/json"]
        self.assertIn('"error":"lease already held"', acquire_error)
        self.assertIn("= 409", acquire_error)

        renew = routes[("PUT", "/api/coordination/leases/{resource}")]
        renew_request = self._joined(
            renew["Integration"]["RequestTemplates"]["application/json"]
        )
        self.assertIn("SET #expires_at = #expires_at + :extension", renew_request)
        self.assertNotIn("#revision", renew_request)
        self.assertIn(
            '"error":"lease owner mismatch"',
            self._joined(
                renew["Integration"]["IntegrationResponses"][0]["ResponseTemplates"][
                    "application/json"
                ]
            ),
        )
        release = routes[("DELETE", "/api/coordination/leases/{resource}")]
        self.assertIn(
            '"error":"lease owner mismatch"',
            self._joined(
                release["Integration"]["IntegrationResponses"][0]["ResponseTemplates"][
                    "application/json"
                ]
            ),
        )
        inspect = routes[("GET", "/api/coordination/leases/{resource}")]
        for template in (
            self._joined(
                renew["Integration"]["IntegrationResponses"][0]["ResponseTemplates"][
                    "application/json"
                ]
            ),
            self._joined(
                release["Integration"]["IntegrationResponses"][0]["ResponseTemplates"][
                    "application/json"
                ]
            ),
            self._joined(
                inspect["Integration"]["IntegrationResponses"][-1]["ResponseTemplates"][
                    "application/json"
                ]
            ),
        ):
            self.assertIn("$util.parseJson($item.expires_at.N)", template)
        for method in (renew, release):
            error_template = self._joined(
                method["Integration"]["IntegrationResponses"][0]["ResponseTemplates"][
                    "application/json"
                ]
            )
            self.assertIn('"error":"no live lease"', error_template)
            self.assertIn("= 404", error_template)

    def test_production_stack_retains_state_and_enables_point_in_time_recovery(
        self,
    ) -> None:
        resources = self._production_template().to_json()["Resources"]
        resource_types = [item["Type"] for item in resources.values()]
        self.assertNotIn("AWS::EC2::VPC", resource_types)
        self.assertNotIn("AWS::EFS::FileSystem", resource_types)

        for item in resources.values():
            if item["Type"] in (
                "AWS::Cognito::UserPool",
                "AWS::IoT::Authorizer",
                "AWS::SecretsManager::Secret",
            ):
                self.assertEqual(item["DeletionPolicy"], "Retain")
                self.assertEqual(item["UpdateReplacePolicy"], "Retain")

        tables = [
            item
            for item in resources.values()
            if item["Type"] == "AWS::DynamoDB::Table"
        ]
        self.assertEqual(len(tables), 2)
        for table in tables:
            self.assertEqual(table["DeletionPolicy"], "Retain")
            self.assertEqual(table["UpdateReplacePolicy"], "Retain")
            self.assertTrue(
                table["Properties"]["PointInTimeRecoverySpecification"][
                    "PointInTimeRecoveryEnabled"
                ]
            )
            self.assertEqual(table["Properties"]["BillingMode"], "PAY_PER_REQUEST")

        table_names = {item["Properties"]["TableName"] for item in tables}
        self.assertEqual(
            table_names,
            {"kanbus-coordination-leases-prod", "kanbus-coordination-mqtt-tokens-prod"},
        )
        authorizer = next(
            item["Properties"]
            for item in resources.values()
            if item["Type"] == "AWS::IoT::Authorizer"
        )
        self.assertEqual(authorizer["AuthorizerName"], "kanbus-mqtt-token-prod")


if __name__ == "__main__":
    unittest.main()
