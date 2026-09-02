"""Template assertions for no-NAT idle-cost architecture."""

import json
import unittest

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from kanbus_cloud.cloud_stack import KanbusCloudFoundationStack


class NoNatIdleCostTemplateTests(unittest.TestCase):
    """Validate NAT removal and Fargate sync topology in synthesized template."""

    @staticmethod
    def _template() -> Template:
        app = App(context={"env_name": "test"})
        stack = KanbusCloudFoundationStack(
            app, "KanbusCloudFoundationNoNatTest", env_name="test"
        )
        return Template.from_stack(stack)

    @staticmethod
    def _rendered_resources(template: Template) -> dict:
        return template.to_json()["Resources"]

    def test_vpc_has_zero_nat_gateways(self) -> None:
        template = self._template()
        template.resource_count_is("AWS::EC2::NatGateway", 0)

    def test_no_load_balancers(self) -> None:
        template = self._template()
        template.resource_count_is("AWS::ElasticLoadBalancingV2::LoadBalancer", 0)
        rendered = self._rendered_resources(template)
        classic_elbs = [
            resource
            for resource in rendered.values()
            if resource["Type"] == "AWS::ElasticLoadBalancing::LoadBalancer"
        ]
        self.assertEqual(classic_elbs, [])

    def test_console_lambda_uses_isolated_subnets(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        isolated_subnet_ids = {
            resource_id
            for resource_id, resource in rendered.items()
            if resource["Type"] == "AWS::EC2::Subnet"
            and any(
                tag.get("Key") == "aws-cdk:subnet-type" and tag.get("Value") == "Isolated"
                for tag in resource["Properties"].get("Tags", [])
            )
        }
        self.assertGreater(len(isolated_subnet_ids), 0)

        console_lambdas = [
            resource
            for resource in rendered.values()
            if resource["Type"] == "AWS::Lambda::Function"
            and resource["Properties"].get("Description", "").startswith("Kanbus console API")
        ]
        self.assertEqual(len(console_lambdas), 1)
        serialized_subnets = json.dumps(console_lambdas[0]["Properties"]["VpcConfig"]["SubnetIds"])
        for subnet_id in isolated_subnet_ids:
            self.assertIn(subnet_id, serialized_subnets)

    def test_efs_nfs_ingress_limited_to_console_and_sync_security_groups(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        ingress_rules = [
            resource
            for resource in rendered.values()
            if resource["Type"] == "AWS::EC2::SecurityGroupIngress"
            and resource["Properties"].get("FromPort") == 2049
            and resource["Properties"].get("ToPort") == 2049
        ]
        self.assertEqual(len(ingress_rules), 2)
        for rule in ingress_rules:
            self.assertIn("SourceSecurityGroupId", rule["Properties"])
            self.assertNotIn("CidrIp", rule["Properties"])

    def test_sync_fargate_task_definition_uses_efs_access_point(self) -> None:
        template = self._template()
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            {
                "RequiresCompatibilities": ["FARGATE"],
                "Volumes": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Name": "tenant-data",
                                "EFSVolumeConfiguration": Match.object_like(
                                    {
                                        "TransitEncryption": "ENABLED",
                                        "AuthorizationConfig": Match.object_like(
                                            {
                                                "IAM": "ENABLED",
                                                "AccessPointId": Match.any_value(),
                                            }
                                        ),
                                    }
                                ),
                            }
                        )
                    ]
                ),
            },
        )

    def test_sync_dispatcher_assigns_public_ip_enabled(self) -> None:
        template = self._template()
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Handler": "sync_dispatcher.handler",
                "Environment": {
                    "Variables": Match.object_like(
                        {
                            "ECS_ASSIGN_PUBLIC_IP": "ENABLED",
                            "ECS_SUBNET_IDS": Match.any_value(),
                            "ECS_SECURITY_GROUP_IDS": Match.any_value(),
                        }
                    )
                },
            },
        )

    def test_sync_dispatcher_uses_public_subnets(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        public_subnet_ids = {
            resource_id
            for resource_id, resource in rendered.items()
            if resource["Type"] == "AWS::EC2::Subnet"
            and any(
                tag.get("Key") == "aws-cdk:subnet-type" and tag.get("Value") == "Public"
                for tag in resource["Properties"].get("Tags", [])
            )
        }
        self.assertGreater(len(public_subnet_ids), 0)

        dispatchers = [
            resource
            for resource in rendered.values()
            if resource["Type"] == "AWS::Lambda::Function"
            and resource["Properties"].get("Handler") == "sync_dispatcher.handler"
        ]
        self.assertEqual(len(dispatchers), 1)
        subnet_value = dispatchers[0]["Properties"]["Environment"]["Variables"]["ECS_SUBNET_IDS"]
        serialized_subnets = json.dumps(subnet_value)
        for subnet_id in public_subnet_ids:
            self.assertIn(subnet_id, serialized_subnets)

    def test_tenant_sync_worker_lambda_removed(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        worker_lambdas = [
            resource_id
            for resource_id, resource in rendered.items()
            if resource["Type"] == "AWS::Lambda::Function"
            and "TenantSyncWorker" in resource_id
        ]
        self.assertEqual(worker_lambdas, [])

    def test_sqs_triggers_dispatcher_not_sync_lambda(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        mappings = [
            resource
            for resource in rendered.values()
            if resource["Type"] == "AWS::Lambda::EventSourceMapping"
        ]
        sync_queue_ids = {
            resource_id
            for resource_id, resource in rendered.items()
            if resource["Type"] == "AWS::SQS::Queue"
            and resource["Properties"].get("QueueName") == "kanbus-sync-test"
        }
        self.assertEqual(len(sync_queue_ids), 1)
        sync_queue_id = next(iter(sync_queue_ids))

        sync_mappings = [
            mapping
            for mapping in mappings
            if mapping["Properties"]["EventSourceArn"]["Fn::GetAtt"][0] == sync_queue_id
        ]
        self.assertEqual(len(sync_mappings), 1)
        function_ref = sync_mappings[0]["Properties"]["FunctionName"]["Ref"]
        dispatcher = rendered[function_ref]
        self.assertEqual(
            dispatcher["Properties"]["Handler"],
            "sync_dispatcher.handler",
        )

    def test_sync_dispatcher_not_in_vpc(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        dispatchers = [
            resource
            for resource in rendered.values()
            if resource["Type"] == "AWS::Lambda::Function"
            and resource["Properties"].get("Handler") == "sync_dispatcher.handler"
        ]
        self.assertEqual(len(dispatchers), 1)
        self.assertNotIn("VpcConfig", dispatchers[0]["Properties"])

    def test_sync_queue_visibility_timeout_exceeds_dispatcher_timeout(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        sync_queues = [
            resource
            for resource in rendered.values()
            if resource["Type"] == "AWS::SQS::Queue"
            and resource["Properties"].get("QueueName") == "kanbus-sync-test"
        ]
        dispatchers = [
            resource
            for resource in rendered.values()
            if resource["Type"] == "AWS::Lambda::Function"
            and resource["Properties"].get("Handler") == "sync_dispatcher.handler"
        ]
        self.assertEqual(len(sync_queues), 1)
        self.assertEqual(len(dispatchers), 1)
        queue_visibility = sync_queues[0]["Properties"]["VisibilityTimeout"]
        dispatcher_timeout = dispatchers[0]["Properties"]["Timeout"]
        self.assertGreater(queue_visibility, dispatcher_timeout)


if __name__ == "__main__":
    unittest.main()
