"""Template assertions for cloud auth and tenant isolation scaffolding."""

import unittest

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from kanbus_cloud.cloud_stack import KanbusCloudFoundationStack


class AuthIsolationTemplateTests(unittest.TestCase):
    """Validate auth/isolation resources in synthesized template."""

    @staticmethod
    def _template() -> Template:
        app = App(context={"env_name": "test"})
        stack = KanbusCloudFoundationStack(app, "KanbusCloudFoundationTest", env_name="test")
        return Template.from_stack(stack)

    def test_token_admin_methods_require_cognito_authorizer(self) -> None:
        template = self._template()
        template.has_resource_properties(
            "AWS::ApiGateway::Method",
            {
                "HttpMethod": "GET",
                "AuthorizationType": "COGNITO_USER_POOLS",
                "AuthorizerId": Match.any_value(),
            },
        )
        template.has_resource_properties(
            "AWS::ApiGateway::Method",
            {
                "HttpMethod": "POST",
                "AuthorizationType": "COGNITO_USER_POOLS",
                "AuthorizerId": Match.any_value(),
            },
        )

    def test_tenant_api_proxy_requires_cognito_authorizer(self) -> None:
        resources = self._template().to_json()["Resources"]
        gateway_resources = {
            logical_id: resource["Properties"]
            for logical_id, resource in resources.items()
            if resource["Type"] == "AWS::ApiGateway::Resource"
        }

        def full_path(logical_id: str) -> str:
            properties = gateway_resources[logical_id]
            parent = properties["ParentId"]
            parent_id = parent.get("Ref") if isinstance(parent, dict) else None
            prefix = full_path(parent_id) if parent_id in gateway_resources else ""
            return f"{prefix}/{properties['PathPart']}"

        authorization_by_path = {}
        for resource in resources.values():
            if resource["Type"] != "AWS::ApiGateway::Method":
                continue
            properties = resource["Properties"]
            resource_ref = properties["ResourceId"]
            logical_id = resource_ref.get("Ref") if isinstance(resource_ref, dict) else None
            if logical_id in gateway_resources:
                authorization_by_path[full_path(logical_id)] = properties["AuthorizationType"]

        self.assertEqual(
            authorization_by_path["/{account}/{project}/api/{proxy+}"],
            "COGNITO_USER_POOLS",
        )
        self.assertEqual(authorization_by_path["/assets/{proxy+}"], "NONE")

    def test_identity_role_includes_tenant_scoped_iot_policy(self) -> None:
        template = self._template()
        rendered = template.to_json()
        policy_docs = [
            res["Properties"]["PolicyDocument"]
            for res in rendered["Resources"].values()
            if res["Type"] == "AWS::IAM::Policy"
        ]
        serialized = str(policy_docs)
        self.assertIn("projects/*/*/events", serialized)
        self.assertIn("iot:Subscribe", serialized)
        self.assertIn("iot:Receive", serialized)

    def test_user_pool_client_enables_oauth_code_grant(self) -> None:
        template = self._template()
        template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            {
                "AllowedOAuthFlowsUserPoolClient": True,
                "AllowedOAuthFlows": Match.array_with(["code"]),
            },
        )

    def test_iot_custom_authorizer_is_provisioned(self) -> None:
        template = self._template()
        template.resource_count_is("AWS::IoT::Authorizer", 1)


if __name__ == "__main__":
    unittest.main()
