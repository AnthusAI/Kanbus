from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import subprocess
import tempfile
from types import SimpleNamespace

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


def test_overlay_time_helpers_cover_tombstone_base_comparisons() -> None:
    now = datetime.now(timezone.utc)
    stale_ts = (now - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    future_ts = (now + timedelta(minutes=2)).isoformat().replace("+00:00", "Z")

    assert overlay_module._tombstone_newer_than_base(future_ts, now) is True
    assert overlay_module._tombstone_newer_than_base(stale_ts, now) is False
    assert overlay_module._tombstone_newer_than_base(stale_ts, None) is True
    assert overlay_module._base_newer_than_tombstone(now, stale_ts) is True
    assert overlay_module._base_newer_than_tombstone(now, "bad-ts") is True


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


def test_gc_overlay_for_projects_selects_default_label(
    monkeypatch, tmp_path: Path
) -> None:
    configuration = SimpleNamespace(
        project_key="alpha",
        overlay=OverlayConfig(enabled=True, ttl_s=120),
    )
    labeled = [
        SimpleNamespace(label="alpha", project_dir=tmp_path / "alpha"),
        SimpleNamespace(label="beta", project_dir=tmp_path / "beta"),
    ]
    monkeypatch.setattr(
        overlay_module, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        overlay_module, "load_project_configuration", lambda _path: configuration
    )
    monkeypatch.setattr(
        overlay_module, "resolve_labeled_projects", lambda _root: labeled
    )
    seen: list[Path] = []
    monkeypatch.setattr(
        overlay_module,
        "gc_overlay",
        lambda project_dir, _config: seen.append(project_dir),
    )
    count = overlay_module.gc_overlay_for_projects(
        tmp_path, project_label=None, all_projects=False
    )
    assert count == 1
    assert seen == [tmp_path / "alpha"]


def test_gc_overlay_for_projects_returns_zero_when_no_projects(
    monkeypatch, tmp_path: Path
) -> None:
    configuration = SimpleNamespace(
        project_key="alpha",
        overlay=OverlayConfig(enabled=True, ttl_s=120),
    )
    monkeypatch.setattr(
        overlay_module, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        overlay_module, "load_project_configuration", lambda _path: configuration
    )
    monkeypatch.setattr(overlay_module, "resolve_labeled_projects", lambda _root: [])
    assert (
        overlay_module.gc_overlay_for_projects(
            tmp_path, project_label=None, all_projects=False
        )
        == 0
    )


def test_reconcile_overlay_for_projects_aggregates_stats(
    monkeypatch, tmp_path: Path
) -> None:
    configuration = SimpleNamespace(
        project_key="alpha",
        overlay=OverlayConfig(enabled=True, ttl_s=120),
    )
    labeled = [
        SimpleNamespace(label="alpha", project_dir=tmp_path / "alpha"),
        SimpleNamespace(label="beta", project_dir=tmp_path / "beta"),
    ]
    monkeypatch.setattr(
        overlay_module, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        overlay_module, "load_project_configuration", lambda _path: configuration
    )
    monkeypatch.setattr(
        overlay_module, "resolve_labeled_projects", lambda _root: labeled
    )
    monkeypatch.setattr(
        overlay_module,
        "reconcile_overlay",
        lambda project_dir, config, prune, dry_run: overlay_module.OverlayReconcileStats(
            issues_scanned=2 if project_dir.name == "alpha" else 3,
            issues_updated=1,
            issues_removed=0,
            fields_pruned=4,
        ),
    )
    stats = overlay_module.reconcile_overlay_for_projects(
        tmp_path,
        project_label=None,
        all_projects=True,
        prune=True,
        dry_run=False,
    )
    assert stats.projects == 2
    assert stats.issues_scanned == 5
    assert stats.issues_updated == 2
    assert stats.fields_pruned == 8


def test_reconcile_overlay_for_projects_rejects_unknown_label(
    monkeypatch, tmp_path: Path
) -> None:
    configuration = SimpleNamespace(
        project_key="alpha",
        overlay=OverlayConfig(enabled=True, ttl_s=120),
    )
    monkeypatch.setattr(
        overlay_module, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        overlay_module, "load_project_configuration", lambda _path: configuration
    )
    monkeypatch.setattr(
        overlay_module,
        "resolve_labeled_projects",
        lambda _root: [SimpleNamespace(label="alpha", project_dir=tmp_path / "alpha")],
    )
    try:
        overlay_module.reconcile_overlay_for_projects(
            tmp_path,
            project_label="missing",
            all_projects=False,
            prune=False,
            dry_run=True,
        )
    except ValueError as error:
        assert "unknown project label" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_resolve_git_hooks_dir_handles_non_repo_and_relative_path(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        overlay_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="nope"),
    )
    try:
        overlay_module._resolve_git_hooks_dir(tmp_path)
    except RuntimeError as error:
        assert "not a git repository" in str(error)
    else:
        raise AssertionError("expected RuntimeError")

    monkeypatch.setattr(
        overlay_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=".git/hooks\n"),
    )
    assert (
        overlay_module._resolve_git_hooks_dir(tmp_path) == tmp_path / ".git" / "hooks"
    )


def test_issue_map_helpers_and_tagging_cover_edges() -> None:
    now = datetime.now(timezone.utc)
    issue = _issue("kanbus-helpers", now)
    issue.custom["source"] = "local"
    issue.custom["last_event_id"] = 123

    tagged = overlay_module._tag_issue(issue, "alpha")
    assert tagged is not None
    assert tagged.custom["source"] == "local"
    assert tagged.custom["project_label"] == "alpha"
    assert overlay_module._extract_event_id(issue) is None

    payload = overlay_module._issue_to_map(issue)
    assert overlay_module._issue_from_map(payload) is not None
    assert overlay_module._issue_from_map({"id": "broken"}) is None


def test_diff_issue_fields_and_remove_path_and_ensure_executable(
    monkeypatch, tmp_path: Path
) -> None:
    now = datetime.now(timezone.utc)
    base = _issue("kanbus-a", now)
    overlay = base.model_copy(update={"title": "Updated title", "priority": 1})
    diff = overlay_module._diff_issue_fields(base, overlay)
    assert diff["title"] == "Updated title"
    assert diff["priority"] == 1

    missing = tmp_path / "missing.json"
    overlay_module._remove_path(missing)
    assert not missing.exists()

    marker = tmp_path / "hook.sh"
    marker.write_text("#!/bin/sh\necho test\n", encoding="utf-8")
    overlay_module._ensure_executable(marker)
    assert marker.stat().st_mode & 0o111 != 0

    monkeypatch.setattr(
        Path,
        "chmod",
        lambda self, _mode: (_ for _ in ()).throw(OSError("denied")),
    )
    overlay_module._ensure_executable(marker)


def test_overlay_path_and_tombstone_round_trip(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    issue = _issue("kanbus-roundtrip", datetime.now(timezone.utc))
    overlay_module.write_overlay_issue(
        project_dir,
        issue,
        "2026-01-01T00:00:00Z",
        "evt-1",
    )
    tombstone = overlay_module.OverlayTombstone(
        op="delete",
        project="alpha",
        id="kanbus-roundtrip",
        event_id="evt-2",
        ts="2026-01-01T00:00:01Z",
        ttl_s=60,
    )
    overlay_module.write_tombstone(project_dir, tombstone)
    loaded_overlay = overlay_module.load_overlay_issue(project_dir, "kanbus-roundtrip")
    loaded_tombstone = overlay_module.load_tombstone(project_dir, "kanbus-roundtrip")
    assert loaded_overlay is not None
    assert loaded_overlay.overlay_event_id == "evt-1"
    assert loaded_tombstone is not None
    assert loaded_tombstone.project == "alpha"
    assert overlay_module.overlay_tombstone_path(
        project_dir, "kanbus-roundtrip"
    ).exists()


def test_resolve_issue_with_overlay_handles_disabled_and_tombstone_paths(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    now = datetime.now(timezone.utc)
    base = _issue("kanbus-resolve", now)
    assert (
        overlay_module.resolve_issue_with_overlay(
            project_dir,
            base,
            None,
            None,
            OverlayConfig(enabled=False, ttl_s=60),
        )
        == base
    )
    tombstone = overlay_module.OverlayTombstone(
        op="delete",
        project="alpha",
        id="kanbus-resolve",
        event_id="evt",
        ts=(now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        ttl_s=60,
    )
    assert (
        overlay_module.resolve_issue_with_overlay(
            project_dir,
            base,
            None,
            tombstone,
            OverlayConfig(enabled=True, ttl_s=60),
        )
        is None
    )


def test_apply_overlay_to_issues_handles_disabled_local_and_overlay_only_entries(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    shared = _issue("kanbus-shared", now)
    local = _issue("kanbus-local", now)
    local.custom["source"] = "local"

    disabled = overlay_module.apply_overlay_to_issues(
        project_dir, [shared, local], OverlayConfig(enabled=False, ttl_s=60)
    )
    assert [item.identifier for item in disabled] == ["kanbus-shared", "kanbus-local"]

    overlay_only = _issue("kanbus-only", now + timedelta(minutes=2))
    overlay_module.write_overlay_issue(
        project_dir,
        overlay_only,
        overlay_only.updated_at.isoformat().replace("+00:00", "Z"),
        "evt-only",
    )
    applied = overlay_module.apply_overlay_to_issues(
        project_dir,
        [shared, local],
        OverlayConfig(enabled=True, ttl_s=3600),
        project_label="alpha",
    )
    identifiers = [item.identifier for item in applied]
    assert "kanbus-local" in identifiers
    assert "kanbus-only" in identifiers
    assert identifiers == sorted(identifiers)


def test_gc_overlay_handles_disabled_and_invalid_overlay_entries(
    monkeypatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "project"
    overlay_issue_dir = project_dir / ".overlay" / "issues"
    overlay_tombstone_dir = project_dir / ".overlay" / "tombstones"
    overlay_issue_dir.mkdir(parents=True, exist_ok=True)
    overlay_tombstone_dir.mkdir(parents=True, exist_ok=True)
    stale_overlay = overlay_issue_dir / "stale.json"
    stale_overlay.write_text("{}", encoding="utf-8")
    stale_tombstone = overlay_tombstone_dir / "stale.json"
    stale_tombstone.write_text("{}", encoding="utf-8")

    overlay_module.gc_overlay(project_dir, OverlayConfig(enabled=False, ttl_s=60))
    assert stale_overlay.exists()

    monkeypatch.setattr(
        overlay_module,
        "load_overlay_issue",
        lambda _project_dir, _issue_id: None,
    )
    monkeypatch.setattr(
        overlay_module,
        "load_tombstone",
        lambda _project_dir, _issue_id: None,
    )
    overlay_module.gc_overlay(project_dir, OverlayConfig(enabled=True, ttl_s=60))
    assert not stale_overlay.exists()
    assert not stale_tombstone.exists()


def test_resolve_issue_with_overlay_covers_expired_and_override_merge_paths(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    now = datetime.now(timezone.utc)
    base = _issue("kanbus-merge", now)
    base.custom["last_event_id"] = "evt-1"
    overlay_issue = _issue("kanbus-merge", now + timedelta(minutes=5))
    overlay_record = overlay_module.OverlayIssueRecord(
        issue=overlay_issue,
        overlay_ts=(now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        overlay_event_id="evt-2",
        overrides={"title": "Merged title"},
    )
    merged = overlay_module.resolve_issue_with_overlay(
        project_dir,
        base,
        overlay_record,
        None,
        OverlayConfig(enabled=True, ttl_s=3600),
        project_label="alpha",
    )
    assert merged is not None
    assert merged.title == "Merged title"
    assert merged.custom["project_label"] == "alpha"

    expired = overlay_module.OverlayIssueRecord(
        issue=overlay_issue,
        overlay_ts=(now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
        overlay_event_id="evt-old",
    )
    resolved = overlay_module.resolve_issue_with_overlay(
        project_dir,
        base,
        expired,
        None,
        OverlayConfig(enabled=True, ttl_s=1),
    )
    assert resolved is not None
    assert resolved.identifier == "kanbus-merge"


def test_apply_overlay_to_issues_skips_base_collision_and_missing_overlay(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    overlay_dir = project_dir / ".overlay" / "issues"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    shared = _issue("kanbus-shared2", now)
    overlay_module.write_overlay_issue(
        project_dir,
        _issue("kanbus-shared2", now + timedelta(minutes=1)),
        (now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "evt-a",
    )
    overlay_module.write_overlay_issue(
        project_dir,
        _issue("kanbus-missing-overlay", now + timedelta(minutes=2)),
        (now + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
        "evt-b",
    )
    real_load = overlay_module.load_overlay_issue
    monkeypatch.setattr(
        overlay_module,
        "load_overlay_issue",
        lambda p, issue_id: (
            None if issue_id == "kanbus-missing-overlay" else real_load(p, issue_id)
        ),
    )
    results = overlay_module.apply_overlay_to_issues(
        project_dir,
        [shared],
        OverlayConfig(enabled=True, ttl_s=3600),
    )
    assert [item.identifier for item in results] == ["kanbus-shared2"]


def test_gc_overlay_removes_expired_and_base_newer_records(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    base_issues = project_dir / "issues"
    base_issues.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    expired_issue = _issue("kanbus-expired", now - timedelta(days=2))
    overlay_module.write_overlay_issue(
        project_dir,
        expired_issue,
        expired_issue.updated_at.isoformat().replace("+00:00", "Z"),
        "evt-expired",
    )

    base_newer = _issue("kanbus-base-newer", now)
    (base_issues / "kanbus-base-newer.json").write_text(
        json.dumps(base_newer.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )
    old_overlay = _issue("kanbus-base-newer", now - timedelta(minutes=20))
    overlay_module.write_overlay_issue(
        project_dir,
        old_overlay,
        old_overlay.updated_at.isoformat().replace("+00:00", "Z"),
        "evt-old",
    )

    tombstone_expired = overlay_module.OverlayTombstone(
        op="delete",
        project="alpha",
        id="kanbus-tomb-expired",
        event_id="evt-t1",
        ts=(now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
        ttl_s=1,
    )
    overlay_module.write_tombstone(project_dir, tombstone_expired)

    tombstone_old = overlay_module.OverlayTombstone(
        op="delete",
        project="alpha",
        id="kanbus-base-newer",
        event_id="evt-t2",
        ts=(now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        ttl_s=3600,
    )
    overlay_module.write_tombstone(project_dir, tombstone_old)

    overlay_module.gc_overlay(project_dir, OverlayConfig(enabled=True, ttl_s=60))
    assert not overlay_module.overlay_issue_path(project_dir, "kanbus-expired").exists()
    assert not overlay_module.overlay_issue_path(
        project_dir, "kanbus-base-newer"
    ).exists()
    assert not overlay_module.overlay_tombstone_path(
        project_dir, "kanbus-tomb-expired"
    ).exists()
    assert not overlay_module.overlay_tombstone_path(
        project_dir, "kanbus-base-newer"
    ).exists()


def test_gc_overlay_tolerates_invalid_base_issue_json(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    base_issues = project_dir / "issues"
    base_issues.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    overlay_module.write_overlay_issue(
        project_dir,
        _issue("kanbus-invalid-base", now),
        now.isoformat().replace("+00:00", "Z"),
        "evt",
    )
    (base_issues / "kanbus-invalid-base.json").write_text("{", encoding="utf-8")
    overlay_module.gc_overlay(project_dir, OverlayConfig(enabled=True, ttl_s=3600))
    assert overlay_module.overlay_issue_path(
        project_dir, "kanbus-invalid-base"
    ).exists()


def test_reconcile_overlay_returns_defaults_for_disabled_or_missing_dir(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    disabled = overlay_module.reconcile_overlay(
        project_dir, OverlayConfig(enabled=False, ttl_s=60), prune=False, dry_run=False
    )
    assert disabled == overlay_module.OverlayReconcileStats()

    enabled_no_dir = overlay_module.reconcile_overlay(
        project_dir, OverlayConfig(enabled=True, ttl_s=60), prune=False, dry_run=False
    )
    assert enabled_no_dir == overlay_module.OverlayReconcileStats()


def test_reconcile_overlay_covers_remove_update_and_dry_run_paths(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    base_issues = project_dir / "issues"
    base_issues.mkdir(parents=True, exist_ok=True)
    overlay_dir = project_dir / ".overlay" / "issues"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    base_same = _issue("kanbus-same", now)
    (base_issues / "kanbus-same.json").write_text(
        json.dumps(base_same.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )
    overlay_module.write_overlay_issue(
        project_dir,
        base_same,
        now.isoformat().replace("+00:00", "Z"),
        "evt-same",
    )

    base_update = _issue("kanbus-update", now)
    (base_issues / "kanbus-update.json").write_text(
        json.dumps(base_update.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )
    changed = base_update.model_copy(update={"title": "Changed"})
    overlay_path = overlay_module.overlay_issue_path(project_dir, "kanbus-update")
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_path.write_text(
        json.dumps(
            {
                "overlay_ts": now.isoformat().replace("+00:00", "Z"),
                "overlay_event_id": "evt-update",
                "overrides": None,
                "issue": changed.model_dump(by_alias=True, mode="json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    orphan_issue = _issue("orphan", now)
    overlay_module.write_overlay_issue(
        project_dir,
        orphan_issue,
        now.isoformat().replace("+00:00", "Z"),
        "evt-orphan",
    )
    missing_base_overlay = overlay_dir / "missing-base.json"
    missing_base_overlay.write_text(
        json.dumps(
            {
                "overlay_ts": now.isoformat().replace("+00:00", "Z"),
                "overlay_event_id": "evt-missing",
                "overrides": {"title": "X"},
                "issue": base_update.model_dump(by_alias=True, mode="json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    invalid_base_overlay = overlay_dir / "invalid-base.json"
    invalid_base_overlay.write_text(
        json.dumps(
            {
                "overlay_ts": now.isoformat().replace("+00:00", "Z"),
                "overlay_event_id": "evt-invalid",
                "overrides": {"title": "Y"},
                "issue": base_update.model_dump(by_alias=True, mode="json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (base_issues / "invalid-base.json").write_text("{", encoding="utf-8")

    real_load = overlay_module.load_overlay_issue
    # Force one path through the overlay_issue is None branch.
    monkeypatch.setattr(
        overlay_module,
        "load_overlay_issue",
        lambda p, issue_id: None if issue_id == "orphan" else real_load(p, issue_id),
    )
    stats = overlay_module.reconcile_overlay(
        project_dir, OverlayConfig(enabled=True, ttl_s=60), prune=True, dry_run=False
    )
    assert stats.issues_scanned >= 2
    assert stats.issues_updated >= 1
    assert stats.issues_removed >= 1
    assert not overlay_module.overlay_issue_path(project_dir, "orphan").exists()
    assert not overlay_module.overlay_issue_path(project_dir, "kanbus-same").exists()
    updated_payload = json.loads(overlay_path.read_text(encoding="utf-8"))
    assert updated_payload["overrides"]["title"] == "Changed"

    dry_run_overlay = overlay_module.overlay_issue_path(project_dir, "kanbus-dry")
    base_dry = _issue("kanbus-dry", now)
    (base_issues / "kanbus-dry.json").write_text(
        json.dumps(base_dry.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )
    dry_run_overlay.parent.mkdir(parents=True, exist_ok=True)
    dry_overlay_issue = base_dry.model_copy(update={"title": "Dry Run Changed"})
    dry_run_overlay.write_text(
        json.dumps(
            {
                "overlay_ts": now.isoformat().replace("+00:00", "Z"),
                "overlay_event_id": "evt-dry",
                "overrides": None,
                "issue": dry_overlay_issue.model_dump(by_alias=True, mode="json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    stats_dry = overlay_module.reconcile_overlay(
        project_dir, OverlayConfig(enabled=True, ttl_s=60), prune=False, dry_run=True
    )
    assert stats_dry.issues_removed >= 0
    assert dry_run_overlay.exists()


def test_overlay_remaining_helper_branches(monkeypatch, tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    assert overlay_module._tag_issue(None, "alpha") is None
    assert overlay_module._parse_ts("") is None
    assert overlay_module._is_expired("2026-01-01T00:00:00Z", 0, now) is False
    assert overlay_module._overlay_is_newer("bad-ts", now, None, None) is False
    assert (
        overlay_module._overlay_is_newer(
            now.isoformat().replace("+00:00", "Z"), now, None, None
        )
        is True
    )
    assert overlay_module._tombstone_newer_than_base("bad-ts", now) is False

    issue = _issue("kanbus-evt", now)
    issue.custom["last_event_id"] = "evt-1"
    assert overlay_module._extract_event_id(issue) == "evt-1"

    marker = tmp_path / "marker.txt"
    marker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        Path,
        "unlink",
        lambda self, missing_ok=True: (_ for _ in ()).throw(OSError("denied")),
    )
    overlay_module._remove_path(marker)


def test_resolve_issue_with_overlay_covers_remove_paths(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    now = datetime.now(timezone.utc)
    base = _issue("kanbus-paths", now)
    overlay_issue = _issue("kanbus-paths", now - timedelta(minutes=1))
    overlay_record = overlay_module.OverlayIssueRecord(
        issue=overlay_issue,
        overlay_ts=overlay_issue.updated_at.isoformat().replace("+00:00", "Z"),
        overlay_event_id="evt-old",
    )
    overlay_module.write_overlay_issue(
        project_dir,
        overlay_issue,
        overlay_record.overlay_ts,
        overlay_record.overlay_event_id,
    )
    result = overlay_module.resolve_issue_with_overlay(
        project_dir,
        base,
        overlay_record,
        None,
        OverlayConfig(enabled=True, ttl_s=3600),
    )
    assert result is not None
    assert result.identifier == "kanbus-paths"
    assert not overlay_module.overlay_issue_path(project_dir, "kanbus-paths").exists()

    tombstone = overlay_module.OverlayTombstone(
        op="delete",
        project="alpha",
        id="kanbus-paths",
        event_id="evt-tomb",
        ts=(now - timedelta(days=2)).isoformat().replace("+00:00", "Z"),
        ttl_s=1,
    )
    overlay_module.write_tombstone(project_dir, tombstone)
    resolved = overlay_module.resolve_issue_with_overlay(
        project_dir,
        base,
        None,
        tombstone,
        OverlayConfig(enabled=True, ttl_s=3600),
    )
    assert resolved is not None
    assert not overlay_module.overlay_tombstone_path(
        project_dir, "kanbus-paths"
    ).exists()


def test_apply_overlay_to_issues_includes_overlay_only_resolved_issue(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    now = datetime.now(timezone.utc)
    shared = _issue("kanbus-base", now)
    overlay_only = _issue("kanbus-overlay-only", now + timedelta(minutes=3))
    overlay_module.write_overlay_issue(
        project_dir,
        overlay_only,
        overlay_only.updated_at.isoformat().replace("+00:00", "Z"),
        "evt-overlay-only",
    )
    result = overlay_module.apply_overlay_to_issues(
        project_dir,
        [shared],
        OverlayConfig(enabled=True, ttl_s=3600),
        project_label="alpha",
    )
    ids = [item.identifier for item in result]
    assert "kanbus-overlay-only" in ids


def test_gc_overlay_tombstone_invalid_base_and_base_newer(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    base_issues = project_dir / "issues"
    base_issues.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    bad_base_tombstone = overlay_module.OverlayTombstone(
        op="delete",
        project="alpha",
        id="kanbus-bad-base",
        event_id="evt-bad",
        ts=(now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
        ttl_s=3600,
    )
    overlay_module.write_tombstone(project_dir, bad_base_tombstone)
    (base_issues / "kanbus-bad-base.json").write_text("{", encoding="utf-8")

    base_new = _issue("kanbus-remove-tomb", now)
    (base_issues / "kanbus-remove-tomb.json").write_text(
        json.dumps(base_new.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )
    removable = overlay_module.OverlayTombstone(
        op="delete",
        project="alpha",
        id="kanbus-remove-tomb",
        event_id="evt-remove",
        ts=(now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        ttl_s=999999,
    )
    overlay_module.write_tombstone(project_dir, removable)
    overlay_module.gc_overlay(project_dir, OverlayConfig(enabled=True, ttl_s=3600))
    assert overlay_module.overlay_tombstone_path(
        project_dir, "kanbus-bad-base"
    ).exists()
    assert not overlay_module.overlay_tombstone_path(
        project_dir, "kanbus-remove-tomb"
    ).exists()


def test_reconcile_overlay_covers_merge_none_and_selector_branches(
    monkeypatch, tmp_path: Path
) -> None:
    project_dir = tmp_path / "project"
    base_issues = project_dir / "issues"
    base_issues.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    base = _issue("kanbus-merge-none", now)
    (base_issues / "kanbus-merge-none.json").write_text(
        json.dumps(base.model_dump(by_alias=True, mode="json"), indent=2),
        encoding="utf-8",
    )
    overlay_module.write_overlay_issue(
        project_dir,
        base.model_copy(update={"title": "Other"}),
        now.isoformat().replace("+00:00", "Z"),
        "evt",
    )
    monkeypatch.setattr(
        overlay_module, "_apply_overrides", lambda *_args, **_kwargs: None
    )
    stats = overlay_module.reconcile_overlay(
        project_dir, OverlayConfig(enabled=True, ttl_s=60), prune=False, dry_run=False
    )
    assert stats.issues_updated == 0

    configuration = SimpleNamespace(
        project_key="alpha",
        overlay=OverlayConfig(enabled=True, ttl_s=60),
    )
    labeled = [SimpleNamespace(label="alpha", project_dir=project_dir)]
    monkeypatch.setattr(
        overlay_module, "get_configuration_path", lambda _root: tmp_path / ".kanbus.yml"
    )
    monkeypatch.setattr(
        overlay_module, "load_project_configuration", lambda _path: configuration
    )
    monkeypatch.setattr(
        overlay_module, "resolve_labeled_projects", lambda _root: labeled
    )
    assert overlay_module.gc_overlay_for_projects(tmp_path, None, True) == 1
    try:
        overlay_module.gc_overlay_for_projects(tmp_path, "missing", False)
    except ValueError as error:
        assert "unknown project label" in str(error)
    else:
        raise AssertionError("expected ValueError")

    monkeypatch.setattr(overlay_module, "resolve_labeled_projects", lambda _root: [])
    assert (
        overlay_module.reconcile_overlay_for_projects(
            tmp_path, None, False, prune=False, dry_run=False
        )
        == overlay_module.OverlayReconcileStats()
    )
    try:
        overlay_module.reconcile_overlay_for_projects(
            tmp_path, "alpha", True, prune=False, dry_run=False
        )
    except ValueError as error:
        assert "cannot combine --project with --all" in str(error)
    else:
        raise AssertionError("expected ValueError")


def test_install_overlay_hooks_appends_block_when_existing_hook_has_other_content(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path
    hooks_dir = root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "post-merge"
    hook.write_text("#!/bin/sh\necho hello\n", encoding="utf-8")
    monkeypatch.setattr(
        overlay_module, "_resolve_git_hooks_dir", lambda _root: hooks_dir
    )
    overlay_module.install_overlay_hooks(root)
    contents = hook.read_text(encoding="utf-8")
    assert "echo hello" in contents
    assert "Kanbus overlay cache maintenance" in contents
