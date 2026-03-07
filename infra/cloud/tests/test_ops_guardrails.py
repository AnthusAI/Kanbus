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
        template.resource_count_is("AWS::CloudWatch::Alarm", 8)
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
        self.assertIn("kanbus-sync-worker-errors-test", serialized_names)
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


if __name__ == "__main__":
    unittest.main()
