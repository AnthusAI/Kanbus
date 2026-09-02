"""Dispatch tenant sync jobs from SQS to on-demand Fargate tasks."""

import json
import os
from typing import Any

import boto3

ECS_ASSIGN_PUBLIC_IP_ENV = "ECS_ASSIGN_PUBLIC_IP"
ECS_CLUSTER_NAME_ENV = "ECS_CLUSTER_NAME"
ECS_CONTAINER_NAME_ENV = "ECS_CONTAINER_NAME"
ECS_SECURITY_GROUP_IDS_ENV = "ECS_SECURITY_GROUP_IDS"
ECS_SUBNET_IDS_ENV = "ECS_SUBNET_IDS"
ECS_TASK_DEFINITION_ENV = "ECS_TASK_DEFINITION"


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise ValueError(f"{name} is not configured")
    return value


def _run_sync_task(ecs_client: Any, job_body: str) -> None:
    cluster = _required_environment(ECS_CLUSTER_NAME_ENV)
    task_definition = _required_environment(ECS_TASK_DEFINITION_ENV)
    container_name = _required_environment(ECS_CONTAINER_NAME_ENV)
    subnets = _required_environment(ECS_SUBNET_IDS_ENV).split(",")
    security_groups = _required_environment(ECS_SECURITY_GROUP_IDS_ENV).split(",")
    assign_public_ip = os.environ.get(ECS_ASSIGN_PUBLIC_IP_ENV, "ENABLED")

    response = ecs_client.run_task(
        cluster=cluster,
        taskDefinition=task_definition,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": subnets,
                "securityGroups": security_groups,
                "assignPublicIp": assign_public_ip,
            }
        },
        overrides={
            "containerOverrides": [
                {
                    "name": container_name,
                    "environment": [{"name": "SYNC_JOB_JSON", "value": job_body}],
                }
            ]
        },
    )
    tasks = response.get("tasks", [])
    if not tasks:
        failures = response.get("failures", [])
        raise RuntimeError(f"ecs RunTask failed: {json.dumps(failures)}")

    task_arn = tasks[0]["taskArn"]
    waiter = ecs_client.get_waiter("tasks_stopped")
    waiter.wait(cluster=cluster, tasks=[task_arn])

    described = ecs_client.describe_tasks(cluster=cluster, tasks=[task_arn])
    task = described["tasks"][0]
    containers = task.get("containers", [])
    if not containers:
        raise RuntimeError(f"sync task produced no containers: {task_arn}")

    exit_code = containers[0].get("exitCode")
    if exit_code != 0:
        reason = containers[0].get("reason", "unknown")
        raise RuntimeError(f"sync task exited with code {exit_code}: {reason}")


def handler(event: dict[str, Any], _context: Any) -> dict[str, str]:
    ecs_client = boto3.client("ecs")

    for record in event.get("Records", []):
        _run_sync_task(ecs_client, record["body"])

    return {"status": "ok"}
