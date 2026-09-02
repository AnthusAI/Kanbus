"""Template assertions for cloud operations alarms and guardrails."""

import unittest

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from kanbus_cloud.cloud_stack import KanbusCloudFoundationStack


class OpsGuardrailsTemplateTests(unittest.TestCase):
    """Validate operations guardrail resources in synthesized template."""

    @staticmethod
    def _template() -> Template:
        app = App(context={"env_name": "test"})
        stack = KanbusCloudFoundationStack(app, "KanbusCloudFoundationOpsTest", env_name="test")
        return Template.from_stack(stack)

    def test_alarm_set_covers_sync_lambda_and_api_paths(self) -> None:
        template = self._template()
        template.resource_count_is("AWS::CloudWatch::Alarm", 10)
        rendered = template.to_json()
        alarm_names = [
            res["Properties"].get("AlarmName", "")
            for res in rendered["Resources"].values()
            if res["Type"] == "AWS::CloudWatch::Alarm"
        ]
        serialized_names = " ".join(alarm_names)
        self.assertIn("kanbus-sync-dlq-visible-test", serialized_names)
        self.assertIn("kanbus-sync-queue-age-test", serialized_names)
        self.assertIn("kanbus-console-lambda-errors-test", serialized_names)
        self.assertIn("kanbus-webhook-lambda-errors-test", serialized_names)
        self.assertIn("kanbus-git-sync-errors-test", serialized_names)
        self.assertIn("kanbus-efs-writer-errors-test", serialized_names)
        self.assertIn("kanbus-sync-notify-errors-test", serialized_names)
        self.assertNotIn("kanbus-sync-worker-errors-test", serialized_names)
        self.assertIn("kanbus-token-admin-errors-test", serialized_names)
        self.assertIn("kanbus-mqtt-authorizer-errors-test", serialized_names)
        self.assertIn("kanbus-console-api-4xx-test", serialized_names)

    def test_api_4xx_alarm_uses_api_gateway_metric(self) -> None:
        template = self._template()
        template.has_resource_properties(
            "AWS::CloudWatch::Alarm",
            {
                "AlarmName": "kanbus-console-api-4xx-test",
                "Namespace": "AWS/ApiGateway",
                "MetricName": "4XXError",
                "Threshold": 20,
                "EvaluationPeriods": 1,
                "ComparisonOperator": "GreaterThanThreshold",
                "Dimensions": Match.array_with(
                    [
                        Match.object_like({"Name": "ApiName"}),
                    ]
                ),
            },
        )

    def test_github_webhook_route_is_path_scoped(self) -> None:
        template = self._template()
        rendered = template.to_json()
        resources = rendered["Resources"]
        path_parts = [
            resource["Properties"].get("PathPart", "")
            for resource in resources.values()
            if resource["Type"] == "AWS::ApiGateway::Resource"
        ]
        self.assertIn("{account}", path_parts)
        self.assertIn("{project}", path_parts)

        resource_ids_by_path_part = {
            resource["Properties"].get("PathPart", ""): logical_id
            for logical_id, resource in resources.items()
            if resource["Type"] == "AWS::ApiGateway::Resource"
        }
        github_resource_id = resource_ids_by_path_part["github"]
        project_resource_id = resource_ids_by_path_part["{project}"]
        github_post_methods = [
            resource
            for resource in resources.values()
            if resource["Type"] == "AWS::ApiGateway::Method"
            and resource["Properties"].get("HttpMethod") == "POST"
            and resource["Properties"]["ResourceId"]["Ref"] == github_resource_id
        ]
        project_post_methods = [
            resource
            for resource in resources.values()
            if resource["Type"] == "AWS::ApiGateway::Method"
            and resource["Properties"].get("HttpMethod") == "POST"
            and resource["Properties"]["ResourceId"]["Ref"] == project_resource_id
        ]
        self.assertEqual(len(github_post_methods), 0)
        self.assertEqual(len(project_post_methods), 1)


if __name__ == "__main__":
    unittest.main()
