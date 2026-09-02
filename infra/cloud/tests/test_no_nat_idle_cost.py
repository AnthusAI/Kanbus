"""Template assertions for no-NAT idle-cost guardrails and S3 bridge sync wiring."""

import json
import unittest

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from kanbus_cloud.cloud_stack import KanbusCloudFoundationStack


class NoNatIdleCostTemplateTests(unittest.TestCase):
    """Validate NAT-free VPC topology and two-lambda S3 bridge sync."""

    @staticmethod
    def _template() -> Template:
        app = App(context={"env_name": "test"})
        stack = KanbusCloudFoundationStack(app, "KanbusCloudFoundationNoNatTest", env_name="test")
        return Template.from_stack(stack)

    @staticmethod
    def _resources(template: Template) -> dict:
        return template.to_json()["Resources"]

    def test_zero_nat_gateways(self) -> None:
        template = self._template()
        template.resource_count_is("AWS::EC2::NatGateway", 0)

    def test_zero_alb_nlb(self) -> None:
        template = self._template()
        template.resource_count_is("AWS::ElasticLoadBalancingV2::LoadBalancer", 0)

    def test_zero_ecs_resources(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        ecs_types = [
            resource_type
            for resource_type in rendered.values()
            if resource_type["Type"].startswith("AWS::ECS::")
        ]
        self.assertEqual(ecs_types, [])

    def test_tenant_sync_worker_removed(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        sync_worker_resources = [
            logical_id
            for logical_id, resource in rendered.items()
            if logical_id.startswith("TenantSyncWorker")
        ]
        self.assertEqual(sync_worker_resources, [])

    def test_git_sync_lambda_not_in_vpc(self) -> None:
        template = self._template()
        template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like(
                {
                    "Description": Match.string_like_regexp("Sync tenant git repos"),
                }
            ),
        )
        rendered = self._resources(template)
        git_sync_functions = [
            resource
            for logical_id, resource in rendered.items()
            if logical_id.startswith("GitSyncLambda")
            and resource["Type"] == "AWS::Lambda::Function"
        ]
        self.assertEqual(len(git_sync_functions), 1)
        self.assertNotIn("VpcConfig", git_sync_functions[0]["Properties"])

    def test_efs_writer_lambda_in_vpc_isolated_with_efs(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        writer_functions = [
            resource
            for logical_id, resource in rendered.items()
            if logical_id.startswith("EfsWriterLambda")
            and resource["Type"] == "AWS::Lambda::Function"
        ]
        self.assertEqual(len(writer_functions), 1)
        properties = writer_functions[0]["Properties"]
        self.assertIn("VpcConfig", properties)
        self.assertIn("FileSystemConfigs", properties)

    def test_efs_writer_has_no_iot_permissions(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        writer_policies = [
            json.dumps(resource.get("Properties", {}))
            for logical_id, resource in rendered.items()
            if logical_id.startswith("EfsWriterLambda") and resource["Type"] == "AWS::IAM::Policy"
        ]
        self.assertTrue(writer_policies)
        serialized = " ".join(writer_policies)
        self.assertNotIn("iot:", serialized)

    def test_efs_writer_has_no_iot_endpoint_env(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        writer_functions = [
            resource
            for logical_id, resource in rendered.items()
            if logical_id.startswith("EfsWriterLambda")
            and resource["Type"] == "AWS::Lambda::Function"
        ]
        environment = writer_functions[0]["Properties"].get("Environment", {}).get("Variables", {})
        self.assertNotIn("KANBUS_IOT_DATA_ENDPOINT", environment)

    def test_sync_notify_lambda_not_in_vpc(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        notify_functions = [
            resource
            for logical_id, resource in rendered.items()
            if logical_id.startswith("SyncNotifyLambda")
            and resource["Type"] == "AWS::Lambda::Function"
        ]
        self.assertEqual(len(notify_functions), 1)
        self.assertNotIn("VpcConfig", notify_functions[0]["Properties"])

    def test_sync_notify_lambda_has_iot_publish(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        notify_policies = [
            json.dumps(resource.get("Properties", {}))
            for logical_id, resource in rendered.items()
            if logical_id.startswith("SyncNotifyLambda") and resource["Type"] == "AWS::IAM::Policy"
        ]
        self.assertTrue(notify_policies)
        serialized = " ".join(notify_policies)
        self.assertIn("iot:Publish", serialized)
        self.assertIn("projects/*/*/events", serialized)

    def test_zero_interface_vpc_endpoints(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        vpc_endpoints = [
            resource
            for resource in rendered.values()
            if resource["Type"] == "AWS::EC2::VPCEndpoint"
        ]
        self.assertEqual(len(vpc_endpoints), 1)
        self.assertEqual(vpc_endpoints[0]["Properties"]["VpcEndpointType"], "Gateway")

    def test_s3_gateway_endpoint_present(self) -> None:
        template = self._template()
        template.has_resource_properties(
            "AWS::EC2::VPCEndpoint",
            {
                "VpcEndpointType": "Gateway",
            },
        )

    def test_sync_bucket_lifecycle_seven_day_expiration(self) -> None:
        template = self._template()
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "LifecycleConfiguration": {
                    "Rules": Match.array_with(
                        [
                            Match.object_like(
                                {
                                    "Id": "ExpireSyncTarballs",
                                    "Status": "Enabled",
                                    "ExpirationInDays": 7,
                                }
                            )
                        ]
                    )
                }
            },
        )

    def test_sqs_triggers_git_sync_lambda_only(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        sqs_mappings = [
            resource
            for logical_id, resource in rendered.items()
            if resource["Type"] == "AWS::Lambda::EventSourceMapping"
            and logical_id.startswith("GitSyncLambda")
        ]
        self.assertEqual(len(sqs_mappings), 1)
        function_name = json.dumps(sqs_mappings[0]["Properties"]["FunctionName"])
        self.assertIn("GitSyncLambda", function_name)

    def test_s3_object_created_triggers_efs_writer_lambda(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        lambda_permissions = [
            resource
            for logical_id, resource in rendered.items()
            if resource["Type"] == "AWS::Lambda::Permission"
            and resource["Properties"].get("Principal") == "s3.amazonaws.com"
            and "EfsWriterLambda" in json.dumps(resource["Properties"].get("FunctionName", ""))
        ]
        self.assertEqual(len(lambda_permissions), 1)

    def test_s3_object_created_triggers_sync_notify_lambda(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        lambda_permissions = [
            resource
            for logical_id, resource in rendered.items()
            if resource["Type"] == "AWS::Lambda::Permission"
            and resource["Properties"].get("Principal") == "s3.amazonaws.com"
        ]
        self.assertEqual(len(lambda_permissions), 2)
        serialized = json.dumps(
            [permission["Properties"].get("FunctionName", "") for permission in lambda_permissions]
        )
        self.assertIn("EfsWriterLambda", serialized)
        self.assertIn("SyncNotifyLambda", serialized)

    def test_efs_security_group_restricts_nfs_to_console_and_writer(self) -> None:
        template = self._template()
        rendered = self._resources(template)
        efs_ingress_rules = [
            resource
            for logical_id, resource in rendered.items()
            if resource["Type"] == "AWS::EC2::SecurityGroupIngress"
            and logical_id.startswith("EfsSecurityGroup")
        ]
        self.assertEqual(len(efs_ingress_rules), 2)
        for rule in efs_ingress_rules:
            properties = rule["Properties"]
            self.assertEqual(properties.get("FromPort"), 2049)
            self.assertEqual(properties.get("ToPort"), 2049)
            self.assertNotEqual(properties.get("CidrIp"), "0.0.0.0/0")
            self.assertIn("SourceSecurityGroupId", properties)


if __name__ == "__main__":
    unittest.main()
