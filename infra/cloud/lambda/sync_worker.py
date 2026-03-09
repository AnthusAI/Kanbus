"""Tenant git sync worker for Kanbus cloud queue messages."""

import fcntl
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import boto3

IOT_TOPIC_TEMPLATE = "projects/{account}/{project}/events"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _repo_root(base: Path, account: str, project: str) -> Path:
    return base / account / project / "repo"


def _sync_repo(repo_root: Path, repo_url: str, sha: str) -> None:
    repo_root.parent.mkdir(parents=True, exist_ok=True)
    if not (repo_root / ".git").exists():
        _run(["git", "clone", "--no-checkout", repo_url, str(repo_root)])
    else:
        pass
    safe_repo = f"safe.directory={repo_root}"
    _run(["git", "-c", safe_repo, "remote", "set-url", "origin", repo_url], cwd=repo_root)
    _run(["git", "-c", safe_repo, "fetch", "--prune", "origin"], cwd=repo_root)
    _run(["git", "-c", safe_repo, "reset", "--hard", sha], cwd=repo_root)


def _publish_sync_event(account: str, project: str, sha: str, ref: str | None) -> None:
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


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    mount = Path(os.environ.get("KANBUS_TENANT_MOUNT", "/mnt/data"))

    for record in event.get("Records", []):
        body = json.loads(record["body"])
        tenant = body["tenant"]
        account = tenant["account"]
        project = tenant["project"]
        repo_url = body["repo_url"]
        sha = body["after_sha"]
        ref = body.get("ref")

        if not repo_url or not sha:
            raise ValueError("repo_url and after_sha are required")

        tenant_root = mount / account / project
        tenant_root.mkdir(parents=True, exist_ok=True)
        lock_path = tenant_root / ".kanbus-sync.lock"

        with lock_path.open("w") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            repo_root = _repo_root(mount, account, project)
            _sync_repo(repo_root, repo_url, sha)
            _publish_sync_event(account, project, sha, ref)

    return {"status": "ok"}
