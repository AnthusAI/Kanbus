"""Non-VPC sync notify lambda: publish IoT events from S3 completion markers."""

import json
from typing import Any
from urllib.parse import unquote_plus

from sync_git_lib import completion_marker_object_key, parse_completion_marker_key, tarball_object_key
from sync_iot_publish import publish_sync_event


def _s3_client():
    import boto3

    return boto3.client("s3")


def _load_marker_payload(bucket_name: str, object_key: str) -> dict[str, Any]:
    response = _s3_client().get_object(Bucket=bucket_name, Key=object_key)
    return json.loads(response["Body"].read().decode("utf-8"))


def _tarball_exists(bucket_name: str, account: str, project: str, sha: str) -> bool:
    from botocore.exceptions import ClientError

    tarball_key = tarball_object_key(account, project, sha)
    try:
        _s3_client().head_object(Bucket=bucket_name, Key=tarball_key)
    except ClientError as error:
        error_code = error.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NotFound", "NoSuchKey"):
            return False
        raise
    return True


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """
    Process S3 completion-marker events and publish IoT sync notifications.

    :param event: S3 notification event containing created object records.
    :type event: dict[str, Any]
    :param _context: Lambda runtime context (unused).
    :type _context: Any
    :return: Handler status payload.
    :rtype: dict[str, Any]
    """
    for record in event.get("Records", []):
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = unquote_plus(record["s3"]["object"]["key"])
        account, project, sha = parse_completion_marker_key(object_key)
        marker = _load_marker_payload(bucket_name, object_key)

        if marker.get("type") != "cloud_sync_completed":
            raise ValueError(f"unexpected marker type for key: {object_key}")
        if marker.get("account") != account or marker.get("project") != project:
            raise ValueError(f"marker coordinates mismatch for key: {object_key}")
        if marker.get("sha") != sha:
            raise ValueError(f"marker sha mismatch for key: {object_key}")

        expected_key = completion_marker_object_key(account, project, sha)
        if object_key != expected_key:
            raise ValueError(f"unexpected marker key: {object_key}")

        if not _tarball_exists(bucket_name, account, project, sha):
            raise ValueError(f"missing tarball for completion marker: {object_key}")

        publish_sync_event(account, project, sha, marker.get("ref"))

    return {"status": "ok"}
