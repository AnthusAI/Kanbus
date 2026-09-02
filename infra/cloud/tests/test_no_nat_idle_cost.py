"""Template assertions for no-NAT idle-cost architecture."""

import json
import unittest

from aws_cdk import App
from aws_cdk.assertions import Match, Template

from kanbus_cloud.cloud_stack import KanbusCloudFoundationStack


class NoNatIdleCostTemplateTests(unittest.TestCase):
    """Validate NAT removal without Fargate in synthesized template."""

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

    @staticmethod
    def _isolated_subnet_ids(rendered: dict) -> set[str]:
        return {
            resource_id
            for resource_id, resource in rendered.items()
            if resource["Type"] == "AWS::EC2::Subnet"
            and any(
                tag.get("Key") == "aws-cdk:subnet-type" and tag.get("Value") == "Isolated"
                for tag in resource["Properties"].get("Tags", [])
            )
        }

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

    def test_zero_ecs_resources(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        ecs_resources = [
            resource_id
            for resource_id, resource in rendered.items()
            if resource["Type"].startswith("AWS::ECS::")
        ]
        self.assertEqual(ecs_resources, [])

    def test_console_lambda_uses_isolated_subnets(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        isolated_subnet_ids = self._isolated_subnet_ids(rendered)
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

    def test_tenant_sync_worker_lambda_uses_isolated_subnets(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        isolated_subnet_ids = self._isolated_subnet_ids(rendered)

        worker_resources = [
            resource
            for resource_id, resource in rendered.items()
            if "TenantSyncWorker" in resource_id
            and resource["Type"] == "AWS::Lambda::Function"
        ]
        self.assertEqual(len(worker_resources), 1)
        serialized_subnets = json.dumps(worker_resources[0]["Properties"]["VpcConfig"]["SubnetIds"])
        for subnet_id in isolated_subnet_ids:
            self.assertIn(subnet_id, serialized_subnets)

    def test_tenant_sync_worker_lambda_is_present(self) -> None:
        template = self._template()
        rendered = self._rendered_resources(template)
        worker_ids = [
            resource_id
            for resource_id, resource in rendered.items()
            if "TenantSyncWorker" in resource_id
            and resource["Type"] == "AWS::Lambda::Function"
        ]
        self.assertEqual(len(worker_ids), 1)

    def test_efs_nfs_ingress_limited_to_console_and_sync_worker_security_groups(self) -> None:
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

    def test_sqs_triggers_sync_worker_not_dispatcher(self) -> None:
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
        worker = rendered[function_ref]
        self.assertIn("TenantSyncWorker", function_ref)

        dispatchers = [
            resource_id
            for resource_id, resource in rendered.items()
            if resource["Type"] == "AWS::Lambda::Function"
            and resource["Properties"].get("Handler") == "sync_dispatcher.handler"
        ]
        self.assertEqual(dispatchers, [])


if __name__ == "__main__":
    unittest.main()
