"""Project rekey: rename a project key and all issue IDs."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

import yaml

from kanbus.models import IssueData
from kanbus.project import (
    get_configuration_path,
    load_project_configuration,
    load_project_directory,
)


class RekeyPlan(NamedTuple):
    """Plan for rekeying a project."""

    old_key: str
    new_key: str
    issue_renames: dict[str, str]
    text_rewrites: dict[str, int]


class RekeyError(Exception):
    """Error during project rekey operation."""

    pass


def _validate_project_key(key: str) -> None:
    """Validate project key format.

    :param key: Project key to validate.
    :type key: str
    :raises RekeyError: If key is invalid.
    """
    if not key or len(key) == 0:
        raise RekeyError("invalid project key: must not be empty")
    if not all(c.isalnum() or c in '-_' for c in key):
        raise RekeyError("invalid project key: contains invalid characters")


def _check_git_tree_clean(root: Path) -> None:
    """Check that project/ directory has no uncommitted changes.

    :param root: Repository root.
    :type root: Path
    :raises RekeyError: If uncommitted changes exist.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "project/"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            raise RekeyError("uncommitted changes under project/")
    except subprocess.CalledProcessError as error:
        if error.returncode != 128:  # not a git error
            raise RekeyError(f"git status check failed: {error}") from error


def _rewrite_id_references(text: str, old_key: str, new_key: str, valid_ids: set[str]) -> tuple[str, int]:
    """Rewrite ID references in text, respecting word boundaries.

    Only rewrites full or short IDs that resolve to existing issues.

    :param text: Text to rewrite.
    :type text: str
    :param old_key: Old project key.
    :type old_key: str
    :param new_key: New project key.
    :type new_key: str
    :param valid_ids: Set of valid issue IDs to rewrite.
    :type valid_ids: set[str]
    :return: Tuple of (rewritten text, count of rewrites).
    :rtype: tuple[str, int]
    """
    rewrite_count = 0

    def replace_id(match: re.Match) -> str:
        nonlocal rewrite_count
        full_match = match.group(0)

        if full_match in valid_ids:
            rewrite_count += 1
            return full_match.replace(old_key, new_key, 1)

        return full_match

    pattern = rf"\b{re.escape(old_key)}-[0-9a-fA-F]{{6,}}\b"
    result = re.sub(pattern, replace_id, text)

    return result, rewrite_count


def plan_rekey(root: Path, old_key: str, new_key: str, dry_run: bool = False) -> RekeyPlan:
    """Plan a project rekey operation.

    :param root: Repository root.
    :type root: Path
    :param old_key: Old project key.
    :type old_key: str
    :param new_key: New project key.
    :type new_key: str
    :param dry_run: If True, don't check git status.
    :type dry_run: bool
    :return: Plan for rekey.
    :rtype: RekeyPlan
    :raises RekeyError: If rekey is not possible.
    """
    if old_key == new_key:
        raise RekeyError("new key equals old key")

    _validate_project_key(new_key)

    if not dry_run:
        _check_git_tree_clean(root)

    project_dir = load_project_directory(root)
    issues_dir = project_dir / "issues"

    old_ids = []
    for issue_path in issues_dir.glob("*.json"):
        issue_id = issue_path.stem
        if issue_id.startswith(old_key + "-"):
            old_ids.append(issue_id)

    issue_renames = {}
    for old_id in sorted(old_ids):
        suffix = old_id[len(old_key) + 1:]
        new_id = f"{new_key}-{suffix}"

        if not dry_run and (project_dir / "issues" / f"{new_id}.json").exists():
            raise RekeyError(f"{new_id} already exists")

        issue_renames[old_id] = new_id

    text_rewrites = {}
    valid_old_ids = set(issue_renames.keys())

    for old_id in sorted(old_ids):
        new_id = issue_renames[old_id]
        text_rewrites[old_id] = 0

    return RekeyPlan(old_key, new_key, issue_renames, text_rewrites)


def execute_rekey(root: Path, plan: RekeyPlan) -> None:
    """Execute a rekey plan.

    :param root: Repository root.
    :type root: Path
    :param plan: Rekey plan.
    :type plan: RekeyPlan
    :raises RekeyError: If execution fails.
    """
    project_dir = load_project_directory(root)
    issues_dir = project_dir / "issues"
    config_path = get_configuration_path(root)

    valid_ids = set(plan.issue_renames.keys())

    for old_id, new_id in sorted(plan.issue_renames.items()):
        old_path = issues_dir / f"{old_id}.json"

        if not old_path.exists():
            continue

        issue_data = json.loads(old_path.read_text(encoding="utf-8"))

        issue_data["id"] = new_id

        if issue_data.get("parent") and plan.old_key in str(issue_data["parent"]):
            old_parent = issue_data["parent"]
            new_parent = old_parent.replace(plan.old_key + "-", plan.new_key + "-", 1)
            if new_parent in plan.issue_renames.values():
                issue_data["parent"] = new_parent

        if "dependencies" in issue_data and issue_data["dependencies"]:
            for dep in issue_data["dependencies"]:
                if "target" in dep and plan.old_key in str(dep["target"]):
                    old_target = dep["target"]
                    if old_target in valid_ids:
                        new_target = plan.issue_renames[old_target]
                        dep["target"] = new_target

        for field in ["title", "description"]:
            if field in issue_data and issue_data[field]:
                rewritten, count = _rewrite_id_references(
                    issue_data[field], plan.old_key, plan.new_key, valid_ids
                )
                issue_data[field] = rewritten
                if count > 0:
                    plan.text_rewrites[old_id] = plan.text_rewrites.get(old_id, 0) + count

        if "comments" in issue_data and issue_data["comments"]:
            for comment in issue_data["comments"]:
                if "body" in comment and comment["body"]:
                    rewritten, count = _rewrite_id_references(
                        comment["body"], plan.old_key, plan.new_key, valid_ids
                    )
                    comment["body"] = rewritten
                    if count > 0:
                        plan.text_rewrites[old_id] = plan.text_rewrites.get(old_id, 0) + count

        new_path = issues_dir / f"{new_id}.json"
        new_path.write_text(
            json.dumps(issue_data, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

        if old_path != new_path:
            old_path.unlink()

    config = load_project_configuration(config_path)
    config.project_key = plan.new_key

    config_dict = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config_dict["project_key"] = plan.new_key

    config_path.write_text(yaml.safe_dump(config_dict, sort_keys=False), encoding="utf-8")

    invalidate_caches(project_dir)


def invalidate_caches(project_dir: Path) -> None:
    """Invalidate caches after rekey.

    :param project_dir: Project directory.
    :type project_dir: Path
    """
    cache_dir = project_dir / ".cache"
    if cache_dir.exists():
        import shutil
        shutil.rmtree(cache_dir)

    index_dir = project_dir / ".index"
    if index_dir.exists():
        import shutil
        shutil.rmtree(index_dir)

    overlay_dir = project_dir / ".overlay"
    if overlay_dir.exists():
        import shutil
        shutil.rmtree(overlay_dir)
