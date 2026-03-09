#!/usr/bin/env python3
"""CDK entrypoint for the Kanbus cloud foundation stack."""

from aws_cdk import App, Environment

from kanbus_cloud.cloud_stack import KanbusCloudFoundationStack

app = App()

stack_name = app.node.try_get_context("stack_name") or "KanbusCloudFoundation"
env_name = app.node.try_get_context("env_name") or "dev"
account = app.node.try_get_context("account")
region = app.node.try_get_context("region")

env = None
if account and region:
    env = Environment(account=account, region=region)

KanbusCloudFoundationStack(
    app,
    stack_name,
    env_name=env_name,
    env=env,
)

app.synth()
