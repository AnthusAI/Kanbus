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


def test_gc_overlay_for_projects_selects_default_label(monkeypatch, tmp_path: Path) -> None:
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
    monkeypatch.setattr(overlay_module, "resolve_labeled_projects", lambda _root: labeled)
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
    monkeypatch.setattr(overlay_module, "resolve_labeled_projects", lambda _root: labeled)
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
    assert overlay_module._resolve_git_hooks_dir(tmp_path) == tmp_path / ".git" / "hooks"


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
    assert overlay_module.overlay_tombstone_path(project_dir, "kanbus-roundtrip").exists()


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
    assert "kanbus-only" not in identifiers
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
