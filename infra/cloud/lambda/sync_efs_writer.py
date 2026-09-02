"""VPC-isolated EFS writer lambda: extract S3 tarballs and publish IoT sync events."""

import fcntl
import json
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

import boto3

IOT_TOPIC_TEMPLATE = "projects/{account}/{project}/events"


def _s3_client():
    return boto3.client("s3")


def parse_tarball_object_key(object_key: str) -> tuple[str, str, str]:
    """
    Parse tenant coordinates and SHA from an S3 tarball object key.

    :param object_key: S3 object key formatted as ``{account}/{project}/{sha}.tar.gz``.
    :type object_key: str
    :return: Tuple of account, project, and SHA.
    :rtype: tuple[str, str, str]
    :raises ValueError: When the key format is unexpected.
    """
    segments = object_key.split("/")
    if len(segments) != 3 or not segments[2].endswith(".tar.gz"):
        raise ValueError(f"unexpected s3 key: {object_key}")
    account = segments[0]
    project = segments[1]
    sha = segments[2][: -len(".tar.gz")]
    return account, project, sha


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


def extract_tarball_to_tenant_root(tarball_path: Path, tenant_root: Path) -> None:
    """
    Extract a repo tarball into the tenant root on EFS.

    :param tarball_path: Local path to the downloaded tarball.
    :type tarball_path: Path
    :param tenant_root: Tenant directory on the EFS mount.
    :type tenant_root: Path
    """
    tenant_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball_path, "r:gz") as archive:
        archive.extractall(path=tenant_root)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """
    Process S3 object-created events by extracting tarballs to EFS.

    :param event: S3 notification event containing created object records.
    :type event: dict[str, Any]
    :param _context: Lambda runtime context (unused).
    :type _context: Any
    :return: Handler status payload.
    :rtype: dict[str, Any]
    """
    mount = Path(os.environ.get("KANBUS_TENANT_MOUNT", "/mnt/data"))
    bucket_name = os.environ["KANBUS_SYNC_BUCKET"]

    for record in event.get("Records", []):
        object_key = unquote_plus(record["s3"]["object"]["key"])
        account, project, sha = parse_tarball_object_key(object_key)
        metadata = _s3_client().head_object(Bucket=bucket_name, Key=object_key).get("Metadata", {})
        ref = metadata.get("ref")

        tenant_root = mount / account / project
        tenant_root.mkdir(parents=True, exist_ok=True)
        lock_path = tenant_root / ".kanbus-sync.lock"

        with tempfile.TemporaryDirectory() as temporary_directory:
            tarball_path = Path(temporary_directory) / f"{sha}.tar.gz"
            _s3_client().download_file(bucket_name, object_key, str(tarball_path))

            with lock_path.open("w") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                extract_tarball_to_tenant_root(tarball_path, tenant_root)
                publish_sync_event(account, project, sha, ref)

    return {"status": "ok"}
