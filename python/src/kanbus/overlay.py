"""Overlay cache helpers for speculative realtime updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import stat
from typing import Iterable, Optional

from kanbus.config_loader import load_project_configuration
from kanbus.models import IssueData, OverlayConfig
from kanbus.project import get_configuration_path, resolve_labeled_projects


@dataclass(frozen=True)
class OverlayIssueRecord:
    """Overlay issue record."""

    issue: IssueData
    overlay_ts: str
    overlay_event_id: Optional[str]


@dataclass(frozen=True)
class OverlayTombstone:
    """Overlay tombstone record."""

    op: str
    project: str
    id: str
    event_id: Optional[str]
    ts: str
    ttl_s: int


def overlay_root(project_dir: Path) -> Path:
    """Return the overlay root directory for a project."""
    return project_dir / ".overlay"


def overlay_issue_path(project_dir: Path, issue_id: str) -> Path:
    return overlay_root(project_dir) / "issues" / f"{issue_id}.json"


def overlay_tombstone_path(project_dir: Path, issue_id: str) -> Path:
    return overlay_root(project_dir) / "tombstones" / f"{issue_id}.json"


def write_overlay_issue(
    project_dir: Path,
    issue: IssueData,
    overlay_ts: str,
    overlay_event_id: Optional[str],
) -> None:
    """Write an overlay issue snapshot."""
    payload = {
        "overlay_ts": overlay_ts,
        "overlay_event_id": overlay_event_id,
        "issue": issue.model_dump(by_alias=True, mode="json"),
    }
    path = overlay_issue_path(project_dir, issue.identifier)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_tombstone(
    project_dir: Path,
    tombstone: OverlayTombstone,
) -> None:
    """Write an overlay tombstone."""
    path = overlay_tombstone_path(project_dir, tombstone.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "op": tombstone.op,
        "project": tombstone.project,
        "id": tombstone.id,
        "event_id": tombstone.event_id,
        "ts": tombstone.ts,
        "ttl_s": tombstone.ttl_s,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_overlay_issue(
    project_dir: Path, issue_id: str
) -> Optional[OverlayIssueRecord]:
    path = overlay_issue_path(project_dir, issue_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    issue = IssueData.model_validate(payload.get("issue", {}))
    return OverlayIssueRecord(
        issue=issue,
        overlay_ts=payload.get("overlay_ts", ""),
        overlay_event_id=payload.get("overlay_event_id"),
    )


def load_tombstone(project_dir: Path, issue_id: str) -> Optional[OverlayTombstone]:
    path = overlay_tombstone_path(project_dir, issue_id)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return OverlayTombstone(
        op=payload.get("op", "delete"),
        project=payload.get("project", ""),
        id=payload.get("id", issue_id),
        event_id=payload.get("event_id"),
        ts=payload.get("ts", ""),
        ttl_s=int(payload.get("ttl_s", 0) or 0),
    )


def resolve_issue_with_overlay(
    project_dir: Path,
    base_issue: Optional[IssueData],
    overlay_issue: Optional[OverlayIssueRecord],
    tombstone: Optional[OverlayTombstone],
    config: OverlayConfig,
    project_label: Optional[str] = None,
) -> Optional[IssueData]:
    """Resolve an issue with overlay and tombstone semantics."""
    if not config.enabled:
        return base_issue

    now = datetime.now(timezone.utc)
    base_updated = base_issue.updated_at if base_issue else None
    base_event_id = None
    if base_issue is not None:
        candidate = base_issue.custom.get("last_event_id")
        if isinstance(candidate, str):
            base_event_id = candidate

    if tombstone:
        if _is_expired(tombstone.ts, tombstone.ttl_s, now):
            _remove_path(overlay_tombstone_path(project_dir, tombstone.id))
            tombstone = None

    if tombstone and _tombstone_newer_than_base(tombstone.ts, base_updated):
        return None

    if overlay_issue:
        if _is_expired(overlay_issue.overlay_ts, config.ttl_s, now):
            _remove_path(overlay_issue_path(project_dir, overlay_issue.issue.identifier))
            overlay_issue = None
        elif base_updated and _overlay_is_newer(
            overlay_issue.overlay_ts,
            base_updated,
            overlay_issue.overlay_event_id,
            base_event_id,
        ):
            return _tag_issue(overlay_issue.issue, project_label)
        elif base_updated and not _overlay_is_newer(
            overlay_issue.overlay_ts,
            base_updated,
            overlay_issue.overlay_event_id,
            base_event_id,
        ):
            _remove_path(overlay_issue_path(project_dir, overlay_issue.issue.identifier))

    return _tag_issue(base_issue, project_label) if base_issue else None


def apply_overlay_to_issues(
    project_dir: Path,
    issues: Iterable[IssueData],
    config: OverlayConfig,
    project_label: Optional[str] = None,
) -> list[IssueData]:
    """Apply overlay rules to a list of issues."""
    if not config.enabled:
        return list(issues)

    base_by_id = {issue.identifier: issue for issue in issues}
    results: list[IssueData] = []

    for issue in issues:
        if issue.custom.get("source") == "local":
            results.append(issue)
            continue
        overlay_issue = load_overlay_issue(project_dir, issue.identifier)
        tombstone = load_tombstone(project_dir, issue.identifier)
        resolved = resolve_issue_with_overlay(
            project_dir,
            issue,
            overlay_issue,
            tombstone,
            config,
            project_label=project_label,
        )
        if resolved is not None:
            results.append(resolved)

    overlay_dir = overlay_root(project_dir) / "issues"
    if overlay_dir.exists():
        for entry in overlay_dir.glob("*.json"):
            issue_id = entry.stem
            if issue_id in base_by_id:
                continue
            overlay_issue = load_overlay_issue(project_dir, issue_id)
            if overlay_issue is None:
                continue
            tombstone = load_tombstone(project_dir, issue_id)
            resolved = resolve_issue_with_overlay(
                project_dir,
                None,
                overlay_issue,
                tombstone,
                config,
                project_label=project_label,
            )
            if resolved is not None:
                results.append(resolved)

    results.sort(key=lambda issue: issue.identifier)
    return results


def gc_overlay(project_dir: Path, config: OverlayConfig) -> None:
    """Sweep overlay entries and remove stale or expired records."""
    if not config.enabled:
        return
    now = datetime.now(timezone.utc)
    issues_dir = overlay_root(project_dir) / "issues"
    tombstones_dir = overlay_root(project_dir) / "tombstones"

    if issues_dir.exists():
        for entry in issues_dir.glob("*.json"):
            issue_id = entry.stem
            overlay_issue = load_overlay_issue(project_dir, issue_id)
            if overlay_issue is None:
                _remove_path(entry)
                continue
            base_path = project_dir / "issues" / f"{issue_id}.json"
            base_issue = None
            if base_path.exists():
                try:
                    base_issue = IssueData.model_validate(
                        json.loads(base_path.read_text(encoding="utf-8"))
                    )
                except Exception:
                    base_issue = None
            if _is_expired(overlay_issue.overlay_ts, config.ttl_s, now):
                _remove_path(entry)
            elif base_issue and not _overlay_is_newer(
                overlay_issue.overlay_ts,
                base_issue.updated_at,
                overlay_issue.overlay_event_id,
                _extract_event_id(base_issue),
            ):
                _remove_path(entry)

    if tombstones_dir.exists():
        for entry in tombstones_dir.glob("*.json"):
            issue_id = entry.stem
            tombstone = load_tombstone(project_dir, issue_id)
            if tombstone is None:
                _remove_path(entry)
                continue
            base_path = project_dir / "issues" / f"{issue_id}.json"
            base_issue = None
            if base_path.exists():
                try:
                    base_issue = IssueData.model_validate(
                        json.loads(base_path.read_text(encoding="utf-8"))
                    )
                except Exception:
                    base_issue = None
            if _is_expired(tombstone.ts, tombstone.ttl_s, now):
                _remove_path(entry)
            elif base_issue and _base_newer_than_tombstone(
                base_issue.updated_at, tombstone.ts
            ):
                _remove_path(entry)


def _tag_issue(issue: Optional[IssueData], project_label: Optional[str]) -> Optional[IssueData]:
    if issue is None:
        return None
    custom = dict(issue.custom)
    custom.setdefault("source", "shared")
    if project_label:
        custom.setdefault("project_label", project_label)
    return issue.model_copy(update={"custom": custom})


def _parse_ts(timestamp: str) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_expired(timestamp: str, ttl_s: int, now: datetime) -> bool:
    if ttl_s <= 0:
        return False
    parsed = _parse_ts(timestamp)
    if parsed is None:
        return False
    return parsed + timedelta(seconds=ttl_s) < now


def _overlay_is_newer(
    overlay_ts: str,
    base_updated: datetime,
    overlay_event_id: Optional[str],
    base_event_id: Optional[str],
) -> bool:
    parsed = _parse_ts(overlay_ts)
    if parsed is None:
        return False
    if parsed > base_updated:
        return True
    if parsed < base_updated:
        return False
    if overlay_event_id and base_event_id:
        return overlay_event_id > base_event_id
    return True


def _tombstone_newer_than_base(
    tombstone_ts: str, base_updated: Optional[datetime]
) -> bool:
    parsed = _parse_ts(tombstone_ts)
    if parsed is None:
        return False
    if base_updated is None:
        return True
    return parsed >= base_updated


def _base_newer_than_tombstone(base_updated: datetime, tombstone_ts: str) -> bool:
    parsed = _parse_ts(tombstone_ts)
    if parsed is None:
        return True
    return base_updated > parsed


def _extract_event_id(issue: IssueData) -> Optional[str]:
    candidate = issue.custom.get("last_event_id")
    if isinstance(candidate, str):
        return candidate
    return None


def _remove_path(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def gc_overlay_for_projects(
    root: Path, project_label: Optional[str], all_projects: bool
) -> int:
    """Run overlay GC for one or more projects."""
    if project_label and all_projects:
        raise ValueError("cannot combine --project with --all")
    configuration = load_project_configuration(get_configuration_path(root))
    labeled = resolve_labeled_projects(root)
    if not labeled:
        return 0
    if all_projects:
        selected = labeled
    else:
        label = project_label or configuration.project_key
        selected = [project for project in labeled if project.label == label]
        if not selected:
            raise ValueError(f"unknown project label: {label}")
    for project in selected:
        gc_overlay(project.project_dir, configuration.overlay)
    return len(selected)


def install_overlay_hooks(root: Path) -> None:
    """Install git hooks to run overlay GC after git operations."""
    hooks_dir = _resolve_git_hooks_dir(root)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_block = _overlay_hook_block()
    for hook in ("post-merge", "post-checkout", "post-rewrite"):
        hook_path = hooks_dir / hook
        if hook_path.exists():
            existing = hook_path.read_text(encoding="utf-8")
            if "Kanbus overlay cache GC" in existing:
                continue
            contents = existing.rstrip() + "\n\n" + hook_block
        else:
            contents = "#!/bin/sh\n" + hook_block
        hook_path.write_text(contents + "\n", encoding="utf-8")
        _ensure_executable(hook_path)


def _resolve_git_hooks_dir(root: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("not a git repository")
    path = Path(result.stdout.strip())
    if not path.is_absolute():
        path = root / path
    return path


def _overlay_hook_block() -> str:
    return "\n".join(
        [
            "# Kanbus overlay cache GC",
            "if command -v kanbus >/dev/null 2>&1; then",
            "  kanbus overlay gc --all >/dev/null 2>&1 || true",
            "elif command -v kbs >/dev/null 2>&1; then",
            "  kbs overlay gc --all >/dev/null 2>&1 || true",
            "fi",
        ]
    )


def _ensure_executable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        return
