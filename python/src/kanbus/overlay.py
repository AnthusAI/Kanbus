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
    overrides: Optional[dict[str, object]] = None


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
        "overrides": None,
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
        overrides=payload.get("overrides"),
    )


@dataclass(frozen=True)
class OverlayReconcileStats:
    """Aggregate overlay reconcile results."""

    projects: int = 0
    issues_scanned: int = 0
    issues_updated: int = 0
    issues_removed: int = 0
    fields_pruned: int = 0


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
            _remove_path(
                overlay_issue_path(project_dir, overlay_issue.issue.identifier)
            )
        elif base_updated and _overlay_is_newer(
            overlay_issue.overlay_ts,
            base_updated,
            overlay_issue.overlay_event_id,
            base_event_id,
        ):
            if (
                base_issue is not None
                and overlay_issue.overrides
                and isinstance(overlay_issue.overrides, dict)
            ):
                merged = _apply_overrides(base_issue, overlay_issue.overrides)
                if merged is not None:
                    return _tag_issue(merged, project_label)
            return _tag_issue(overlay_issue.issue, project_label)
        elif base_updated and not _overlay_is_newer(
            overlay_issue.overlay_ts,
            base_updated,
            overlay_issue.overlay_event_id,
            base_event_id,
        ):
            _remove_path(
                overlay_issue_path(project_dir, overlay_issue.issue.identifier)
            )
        elif base_issue is None:
            return _tag_issue(overlay_issue.issue, project_label)

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


def reconcile_overlay(
    project_dir: Path,
    config: OverlayConfig,
    prune: bool,
    dry_run: bool,
) -> OverlayReconcileStats:
    """Reconcile overlay snapshots against canonical issue files."""
    stats = OverlayReconcileStats()
    if not config.enabled:
        return stats
    issues_dir = overlay_root(project_dir) / "issues"
    if not issues_dir.exists():
        return stats

    issues_scanned = 0
    issues_updated = 0
    issues_removed = 0
    fields_pruned = 0

    for entry in issues_dir.glob("*.json"):
        issue_id = entry.stem
        overlay_issue = load_overlay_issue(project_dir, issue_id)
        if overlay_issue is None:
            if not dry_run:
                _remove_path(entry)
            continue
        base_path = project_dir / "issues" / f"{issue_id}.json"
        if not base_path.exists():
            continue
        try:
            base_issue = IssueData.model_validate(
                json.loads(base_path.read_text(encoding="utf-8"))
            )
        except Exception:
            continue

        issues_scanned += 1
        overrides = (
            dict(overlay_issue.overrides)
            if isinstance(overlay_issue.overrides, dict)
            else _diff_issue_fields(base_issue, overlay_issue.issue)
        )
        if prune:
            before = len(overrides)
            base_values = _issue_to_map(base_issue)
            overrides = {
                key: value
                for key, value in overrides.items()
                if base_values.get(key) != value
            }
            fields_pruned += before - len(overrides)
        if not overrides:
            issues_removed += 1
            if not dry_run:
                _remove_path(entry)
            continue

        merged_issue = _apply_overrides(base_issue, overrides)
        if merged_issue is None:
            continue
        needs_write = merged_issue != overlay_issue.issue or dict(overrides) != dict(
            overlay_issue.overrides or {}
        )
        if needs_write:
            issues_updated += 1
            if not dry_run:
                payload = {
                    "overlay_ts": overlay_issue.overlay_ts,
                    "overlay_event_id": overlay_issue.overlay_event_id,
                    "overrides": overrides,
                    "issue": merged_issue.model_dump(by_alias=True, mode="json"),
                }
                entry.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return OverlayReconcileStats(
        projects=0,
        issues_scanned=issues_scanned,
        issues_updated=issues_updated,
        issues_removed=issues_removed,
        fields_pruned=fields_pruned,
    )


def _tag_issue(
    issue: Optional[IssueData], project_label: Optional[str]
) -> Optional[IssueData]:
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


def reconcile_overlay_for_projects(
    root: Path,
    project_label: Optional[str],
    all_projects: bool,
    prune: bool,
    dry_run: bool,
) -> OverlayReconcileStats:
    """Run overlay reconcile for one or more projects."""
    if project_label and all_projects:
        raise ValueError("cannot combine --project with --all")
    configuration = load_project_configuration(get_configuration_path(root))
    labeled = resolve_labeled_projects(root)
    if not labeled:
        return OverlayReconcileStats()
    if all_projects:
        selected = labeled
    else:
        label = project_label or configuration.project_key
        selected = [project for project in labeled if project.label == label]
        if not selected:
            raise ValueError(f"unknown project label: {label}")
    aggregate = OverlayReconcileStats(projects=len(selected))
    for project in selected:
        stats = reconcile_overlay(
            project.project_dir, configuration.overlay, prune=prune, dry_run=dry_run
        )
        aggregate = OverlayReconcileStats(
            projects=aggregate.projects,
            issues_scanned=aggregate.issues_scanned + stats.issues_scanned,
            issues_updated=aggregate.issues_updated + stats.issues_updated,
            issues_removed=aggregate.issues_removed + stats.issues_removed,
            fields_pruned=aggregate.fields_pruned + stats.fields_pruned,
        )
    return aggregate


def install_overlay_hooks(root: Path) -> None:
    """Install git hooks to run overlay reconcile/gc after git operations."""
    hooks_dir = _resolve_git_hooks_dir(root)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_block = _overlay_hook_block()
    for hook in ("post-merge", "post-checkout", "post-rewrite"):
        hook_path = hooks_dir / hook
        if hook_path.exists():
            existing = hook_path.read_text(encoding="utf-8")
            if (
                "Kanbus overlay cache maintenance" in existing
                or "Kanbus overlay cache GC" in existing
            ):
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
    if path == Path("/dev/null"):
        raise RuntimeError(
            "git hooks are disabled (core.hooksPath=/dev/null); run `git config --unset core.hooksPath` to enable hook installation"
        )
    if path.exists() and not path.is_dir():
        raise RuntimeError(f"git hooks path is not a directory: {path}")
    return path


def _overlay_hook_block() -> str:
    return "\n".join(
        [
            "# Kanbus overlay cache maintenance",
            "if command -v kanbus >/dev/null 2>&1; then",
            "  kanbus overlay reconcile --all --prune >/dev/null 2>&1 || true",
            "  kanbus overlay gc --all >/dev/null 2>&1 || true",
            "elif command -v kbs >/dev/null 2>&1; then",
            "  kbs overlay reconcile --all --prune >/dev/null 2>&1 || true",
            "  kbs overlay gc --all >/dev/null 2>&1 || true",
            "fi",
        ]
    )


def _issue_to_map(issue: IssueData) -> dict[str, object]:
    return dict(issue.model_dump(by_alias=True, mode="json"))


def _issue_from_map(payload: dict[str, object]) -> Optional[IssueData]:
    try:
        return IssueData.model_validate(payload)
    except Exception:
        return None


def _apply_overrides(
    base_issue: IssueData, overrides: dict[str, object]
) -> Optional[IssueData]:
    merged = _issue_to_map(base_issue)
    merged.update(overrides)
    return _issue_from_map(merged)


def _diff_issue_fields(
    base_issue: IssueData, overlay_issue: IssueData
) -> dict[str, object]:
    base_payload = _issue_to_map(base_issue)
    overlay_payload = _issue_to_map(overlay_issue)
    return {
        key: value
        for key, value in overlay_payload.items()
        if base_payload.get(key) != value
    }


def _ensure_executable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        return
