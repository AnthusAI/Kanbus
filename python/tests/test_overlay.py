from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
import tempfile

import kanbus.overlay as overlay_module
from kanbus.models import IssueData, OverlayConfig
from kanbus.overlay import (
    OverlayIssueRecord,
    gc_overlay,
    install_overlay_hooks,
    reconcile_overlay,
    overlay_issue_path,
    resolve_issue_with_overlay,
    write_overlay_issue,
)


def _issue(identifier: str, updated_at: datetime) -> IssueData:
    return IssueData(
        id=identifier,
        title="Overlay test",
        description="",
        type="task",
        status="open",
        priority=2,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[],
        comments=[],
        created_at=updated_at,
        updated_at=updated_at,
        closed_at=None,
        custom={},
    )


def test_overlay_prefers_newer_overlay() -> None:
    base_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    overlay_time = base_time + timedelta(hours=1)
    base_issue = _issue("kanbus-1", base_time)
    overlay_issue = _issue("kanbus-1", overlay_time)
    overlay_record = OverlayIssueRecord(
        issue=overlay_issue,
        overlay_ts=overlay_time.isoformat().replace("+00:00", "Z"),
        overlay_event_id=None,
    )
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "project"
        project_dir.mkdir(parents=True, exist_ok=True)
        result = resolve_issue_with_overlay(
            project_dir,
            base_issue,
            overlay_record,
            None,
            OverlayConfig(enabled=True, ttl_s=86400),
        )
    assert result is not None
    assert result.identifier == overlay_issue.identifier
    assert result.updated_at == overlay_issue.updated_at


def test_gc_overlay_removes_stale_overlay() -> None:
    base_time = datetime.now(timezone.utc)
    overlay_time = base_time - timedelta(hours=1)
    base_issue = _issue("kanbus-2", base_time)
    overlay_issue = _issue("kanbus-2", overlay_time)
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "project"
        issues_dir = project_dir / "issues"
        issues_dir.mkdir(parents=True, exist_ok=True)
        issue_path = issues_dir / "kanbus-2.json"
        issue_path.write_text(
            json.dumps(base_issue.model_dump(by_alias=True, mode="json"), indent=2),
            encoding="utf-8",
        )
        write_overlay_issue(
            project_dir,
            overlay_issue,
            overlay_time.isoformat().replace("+00:00", "Z"),
            None,
        )
        gc_overlay(project_dir, OverlayConfig(enabled=True, ttl_s=86400))
        assert not overlay_issue_path(project_dir, "kanbus-2").exists()


def test_reconcile_prunes_and_removes_resolved_overlay() -> None:
    base_time = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp) / "project"
        issues_dir = project_dir / "issues"
        issues_dir.mkdir(parents=True, exist_ok=True)
        base_issue = _issue("kanbus-3", base_time)
        issue_path = issues_dir / "kanbus-3.json"
        issue_path.write_text(
            json.dumps(base_issue.model_dump(by_alias=True, mode="json"), indent=2),
            encoding="utf-8",
        )
        overlay_path = overlay_issue_path(project_dir, "kanbus-3")
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "overlay_ts": base_time.isoformat().replace("+00:00", "Z"),
            "overlay_event_id": "evt-1",
            "overrides": {"title": "Overlay test"},
            "issue": base_issue.model_dump(by_alias=True, mode="json"),
        }
        overlay_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        stats = reconcile_overlay(
            project_dir,
            OverlayConfig(enabled=True, ttl_s=86400),
            prune=True,
            dry_run=False,
        )
        assert stats.issues_scanned == 1
        assert stats.issues_removed == 1
        assert stats.fields_pruned == 1
        assert not overlay_path.exists()


def test_install_overlay_hooks_creates_and_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)

        install_overlay_hooks(root)
        install_overlay_hooks(root)

        hook_path = root / ".git" / "hooks" / "post-merge"
        contents = hook_path.read_text(encoding="utf-8")
        assert "# Kanbus overlay cache maintenance" in contents
        assert contents.count("# Kanbus overlay cache maintenance") == 1
        assert hook_path.stat().st_mode & 0o111 != 0


def test_install_overlay_hooks_fails_when_hooks_disabled() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "core.hooksPath", "/dev/null"],
            cwd=root,
            check=True,
            capture_output=True,
        )

        try:
            install_overlay_hooks(root)
        except RuntimeError as error:
            assert "core.hooksPath=/dev/null" in str(error)
        else:
            raise AssertionError("expected RuntimeError")


def test_install_overlay_hooks_fails_when_hooks_path_is_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
        hooks_file = root / "hooks-file"
        hooks_file.write_text("not a directory\n", encoding="utf-8")
        subprocess.run(
            ["git", "config", "core.hooksPath", "hooks-file"],
            cwd=root,
            check=True,
            capture_output=True,
        )

        try:
            install_overlay_hooks(root)
        except RuntimeError as error:
            assert "not a directory" in str(error)
        else:
            raise AssertionError("expected RuntimeError")


def test_overlay_time_helpers_handle_invalid_and_equal_timestamps() -> None:
    now = datetime.now(timezone.utc)

    assert overlay_module._parse_ts("not-a-timestamp") is None
    assert not overlay_module._is_expired("not-a-timestamp", 10, now)
    assert overlay_module._overlay_is_newer(
        now.isoformat().replace("+00:00", "Z"),
        now,
        "evt-2",
        "evt-1",
    )


def test_overlay_hook_block_contains_kanbus_and_kbs_commands() -> None:
    block = overlay_module._overlay_hook_block()
    assert "kanbus overlay reconcile --all --prune" in block
    assert "kbs overlay gc --all" in block


def test_apply_overrides_returns_none_for_invalid_issue_payload() -> None:
    issue = _issue("kanbus-9", datetime.now(timezone.utc))
    # Priority must be an integer, so this payload cannot validate to IssueData.
    result = overlay_module._apply_overrides(issue, {"priority": "invalid"})
    assert result is None


def test_project_reconcile_gc_reject_conflicting_selector_flags() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        try:
            overlay_module.gc_overlay_for_projects(
                root, project_label="alpha", all_projects=True
            )
        except ValueError as error:
            assert "cannot combine --project with --all" in str(error)
        else:
            raise AssertionError("expected ValueError")

        try:
            overlay_module.reconcile_overlay_for_projects(
                root,
                project_label="alpha",
                all_projects=True,
                prune=True,
                dry_run=False,
            )
        except ValueError as error:
            assert "cannot combine --project with --all" in str(error)
        else:
            raise AssertionError("expected ValueError")
