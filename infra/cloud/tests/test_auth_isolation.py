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
