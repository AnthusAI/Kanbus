"""Publish cloud sync completion events to tenant IoT topics."""

import json
import os

import boto3

IOT_TOPIC_TEMPLATE = "projects/{account}/{project}/events"


def publish_sync_event(account: str, project: str, sha: str, ref: str | None) -> None:
    """
    Publish a cloud sync completion event to the tenant IoT topic.

    :param account: Tenant account identifier.
    :type account: str
    :param project: Tenant project identifier.
    :type project: str
    :param sha: Synced commit SHA.
    :type sha: str
    :param ref: Git ref from sync metadata, if present.
    :type ref: str | None
    """
    endpoint = os.environ.get("KANBUS_IOT_DATA_ENDPOINT", "")
    iot_data = (
        boto3.client("iot-data", endpoint_url=f"https://{endpoint}")
        if endpoint
        else boto3.client("iot-data")
    )
    topic = IOT_TOPIC_TEMPLATE.format(account=account, project=project)
    payload = {
        "type": "cloud_sync_completed",
        "account": account,
        "project": project,
        "ref": ref,
        "sha": sha,
    }
    iot_data.publish(topic=topic, qos=0, payload=json.dumps(payload).encode("utf-8"))
