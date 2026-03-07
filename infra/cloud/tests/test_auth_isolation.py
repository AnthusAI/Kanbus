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

    def test_proxy_methods_require_cognito_authorizer(self) -> None:
        template = self._template()
        template.has_resource_properties(
            "AWS::ApiGateway::Method",
            {
                "HttpMethod": "ANY",
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
        self.assertIn("projects/${aws:PrincipalTag/account}/${aws:PrincipalTag/project}/events", serialized)
        self.assertIn("iot:Subscribe", serialized)
        self.assertIn("iot:Receive", serialized)


if __name__ == "__main__":
    unittest.main()
