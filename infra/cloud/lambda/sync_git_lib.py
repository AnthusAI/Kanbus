"""Shared git sync helpers for Kanbus cloud tarball materialization."""

import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SyncJob:
    """Validated tenant sync job fields from an SQS message body."""

    account: str
    project: str
    repo_url: str
    sha: str
    ref: str | None


def parse_sync_job(body: dict) -> SyncJob:
    """
    Parse and validate a sync queue message body.

    :param body: Decoded SQS message body.
    :type body: dict
    :return: Validated sync job fields.
    :rtype: SyncJob
    :raises ValueError: When required fields are missing.
    """
    tenant = body["tenant"]
    account = tenant["account"]
    project = tenant["project"]
    repo_url = body["repo_url"]
    sha = body["after_sha"]
    ref = body.get("ref")
    if not repo_url or not sha:
        raise ValueError("repo_url and after_sha are required")
    return SyncJob(
        account=account,
        project=project,
        repo_url=repo_url,
        sha=sha,
        ref=ref,
    )


def tarball_object_key(account: str, project: str, sha: str) -> str:
    """
    Build the S3 object key for a tenant repo tarball.

    :param account: Tenant account identifier.
    :type account: str
    :param project: Tenant project identifier.
    :type project: str
    :param sha: Git commit SHA synced into the tarball.
    :type sha: str
    :return: S3 object key ending in ``.tar.gz``.
    :rtype: str
    """
    return f"{account}/{project}/{sha}.tar.gz"


def _run(command: list[str], working_directory: Path | None = None) -> None:
    subprocess.run(
        command,
        cwd=str(working_directory) if working_directory else None,
        check=True,
    )


def sync_repo(repo_root: Path, repo_url: str, sha: str) -> None:
    """
    Clone or update a git repository and reset it to the requested SHA.

    :param repo_root: Destination path for the repository working tree.
    :type repo_root: Path
    :param repo_url: Remote repository URL.
    :type repo_url: str
    :param sha: Commit SHA to hard-reset to.
    :type sha: str
    """
    repo_root.parent.mkdir(parents=True, exist_ok=True)
    if not (repo_root / ".git").exists():
        _run(["git", "clone", "--no-checkout", repo_url, str(repo_root)])
    safe_repo = f"safe.directory={repo_root}"
    _run(
        ["git", "-c", safe_repo, "remote", "set-url", "origin", repo_url],
        working_directory=repo_root,
    )
    _run(
        ["git", "-c", safe_repo, "fetch", "--prune", "origin"],
        working_directory=repo_root,
    )
    _run(
        ["git", "-c", safe_repo, "reset", "--hard", sha],
        working_directory=repo_root,
    )


def materialize_repo_tarball(
    work_directory: Path,
    account: str,
    project: str,
    repo_url: str,
    sha: str,
) -> Path:
    """
    Sync a repository into a temporary workspace and archive it as a tarball.

    :param work_directory: Writable parent directory for sync scratch space.
    :type work_directory: Path
    :param account: Tenant account identifier.
    :type account: str
    :param project: Tenant project identifier.
    :type project: str
    :param repo_url: Remote repository URL.
    :type repo_url: str
    :param sha: Commit SHA to sync.
    :type sha: str
    :return: Path to the generated ``{sha}.tar.gz`` archive.
    :rtype: Path
    """
    tenant_work_root = work_directory / account / project
    repo_root = tenant_work_root / "repo"
    sync_repo(repo_root, repo_url, sha)
    tarball_path = tenant_work_root / f"{sha}.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as archive:
        archive.add(repo_root, arcname="repo")
    return tarball_path
