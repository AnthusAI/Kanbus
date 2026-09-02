"""Non-VPC git sync lambda: materialize tenant repos and upload tarballs to S3."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from sync_git_lib import materialize_repo_tarball, parse_sync_job, tarball_object_key


def _s3_client():
    import boto3

    return boto3.client("s3")


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """
    Process SQS sync jobs by syncing git repos and uploading tarballs to S3.

    :param event: SQS event containing sync job records.
    :type event: dict[str, Any]
    :param _context: Lambda runtime context (unused).
    :type _context: Any
    :return: Handler status payload.
    :rtype: dict[str, Any]
    """
    bucket_name = os.environ["KANBUS_SYNC_BUCKET"]

    for record in event.get("Records", []):
        job = parse_sync_job(json.loads(record["body"]))
        with tempfile.TemporaryDirectory() as temporary_directory:
            tarball_path = materialize_repo_tarball(
                Path(temporary_directory),
                job.account,
                job.project,
                job.repo_url,
                job.sha,
            )
            object_key = tarball_object_key(job.account, job.project, job.sha)
            metadata = {"ref": job.ref} if job.ref else {}
            with tarball_path.open("rb") as tarball_file:
                _s3_client().put_object(
                    Bucket=bucket_name,
                    Key=object_key,
                    Body=tarball_file,
                    Metadata=metadata,
                )

    return {"status": "ok"}
