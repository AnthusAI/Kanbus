"""VPC-isolated EFS writer lambda: extract S3 tarballs and write completion markers."""

import fcntl
import json
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

import boto3

from sync_git_lib import completion_marker_object_key, parse_tarball_object_key


def _s3_client():
    return boto3.client("s3")


def completion_marker_payload(
    account: str,
    project: str,
    sha: str,
    ref: str | None,
) -> dict[str, str | None]:
    """
    Build the JSON payload stored in an S3 completion marker.

    :param account: Tenant account identifier.
    :type account: str
    :param project: Tenant project identifier.
    :type project: str
    :param sha: Synced commit SHA.
    :type sha: str
    :param ref: Git ref from sync metadata, if present.
    :type ref: str | None
    :return: Completion marker body fields.
    :rtype: dict[str, str | None]
    """
    return {
        "type": "cloud_sync_completed",
        "account": account,
        "project": project,
        "ref": ref,
        "sha": sha,
    }


def write_completion_marker(
    bucket_name: str,
    account: str,
    project: str,
    sha: str,
    ref: str | None,
) -> None:
    """
    Write an S3 completion marker after a successful EFS extract.

    :param bucket_name: Sync tarball bucket name.
    :type bucket_name: str
    :param account: Tenant account identifier.
    :type account: str
    :param project: Tenant project identifier.
    :type project: str
    :param sha: Synced commit SHA.
    :type sha: str
    :param ref: Git ref from sync metadata, if present.
    :type ref: str | None
    """
    object_key = completion_marker_object_key(account, project, sha)
    body = json.dumps(completion_marker_payload(account, project, sha, ref)).encode("utf-8")
    _s3_client().put_object(Bucket=bucket_name, Key=object_key, Body=body)


def _resolved_member_path(tenant_root: Path, member_name: str) -> Path:
    member_path = (tenant_root / member_name).resolve()
    tenant_root_resolved = tenant_root.resolve()
    if member_path == tenant_root_resolved:
        return member_path
    if tenant_root_resolved not in member_path.parents:
        raise ValueError(f"unsafe tar member path: {member_name}")
    return member_path


def extract_tarball_to_tenant_root(tarball_path: Path, tenant_root: Path) -> None:
    """
    Extract a repo tarball into the tenant root on EFS.

    :param tarball_path: Local path to the downloaded tarball.
    :type tarball_path: Path
    :param tenant_root: Tenant directory on the EFS mount.
    :type tenant_root: Path
    :raises ValueError: When a tarball member would escape ``tenant_root``.
    """
    tenant_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball_path, "r:gz") as archive:
        for member in archive.getmembers():
            _resolved_member_path(tenant_root, member.name)
        for member in archive.getmembers():
            destination_path = _resolved_member_path(tenant_root, member.name)
            if member.isdir():
                destination_path.mkdir(parents=True, exist_ok=True)
                continue
            if member.issym() or member.islnk():
                raise ValueError(f"unsupported tar member type: {member.name}")
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"unable to extract tar member: {member.name}")
            destination_path.write_bytes(extracted.read())


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
                write_completion_marker(bucket_name, account, project, sha, ref)

    return {"status": "ok"}
