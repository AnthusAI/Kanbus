from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from kanbus import cli
from kanbus.config_loader import ConfigurationError
from kanbus.daemon_client import DaemonClientError
from kanbus.dependencies import DependencyError
from kanbus.doctor import DoctorError
from kanbus.gossip import GossipError
from kanbus.jira_sync import JiraSyncError
from kanbus.migration import MigrationError
from kanbus.models import JiraConfiguration, SnykConfiguration
from kanbus.overlay import OverlayReconcileStats
from kanbus.project import ProjectMarkerError
from kanbus.snyk_sync import SnykPullResult, SnykSyncError

from test_helpers import build_issue, build_project_configuration


def _run(args: list[str]) -> object:
    return CliRunner().invoke(cli.cli, args)


def test_dep_tree_and_usage_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    result_tree_missing = _run(["dep", "tree"])
    assert result_tree_missing.exit_code != 0
    assert "tree requires an identifier" in result_tree_missing.output

    result_tree_bad_depth = _run(["dep", "tree", "kanbus-1", "--depth", "x"])
    assert result_tree_bad_depth.exit_code != 0
    assert "depth must be a number" in result_tree_bad_depth.output

    monkeypatch.setattr(cli, "build_dependency_tree", lambda *_a: {"tree": True})
    monkeypatch.setattr(cli, "render_dependency_tree", lambda tree, fmt: f"rendered {fmt}")
    result_tree = _run(["dep", "tree", "kanbus-1", "--format", "json"])
    assert result_tree.exit_code == 0
    assert "rendered json" in result_tree.output

    monkeypatch.setattr(
        cli,
        "build_dependency_tree",
        lambda *_a: (_ for _ in ()).throw(cli.DependencyTreeError("tree fail")),
    )
    result_tree_fail = _run(["dep", "tree", "kanbus-1"])
    assert result_tree_fail.exit_code != 0
    assert "tree fail" in result_tree_fail.output

    result_usage = _run(["dep", "kanbus-1"])
    assert result_usage.exit_code != 0
    assert "usage" in result_usage.output.lower()

    result_remove_missing_target = _run(["dep", "kanbus-1", "remove", "blocked-by"])
    assert result_remove_missing_target.exit_code != 0
    assert "dependency target is required" in result_remove_missing_target.output

    result_add_missing_target = _run(["dep", "kanbus-1", "blocked-by"])
    assert result_add_missing_target.exit_code != 0
    assert "dependency target is required" in result_add_missing_target.output


def test_dep_add_remove_paths_with_modes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        cli,
        "_run_lifecycle_hooks_for_context",
        lambda context, phase, event, operation, root, beads_mode, issues_for_policy=None: calls.append((phase.value, operation["action"])),
    )

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: build_project_configuration(beads_compatibility=True),
    )
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    added: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        "kanbus.beads_write.add_beads_dependency",
        lambda _r, i, t, d: added.append((i, t, d)),
    )

    result_add_beads = _run(["dep", "kanbus-1", "blocked-by", "kanbus-2"])
    assert result_add_beads.exit_code == 0
    assert added == [("kanbus-1", "kanbus-2", "blocked-by")]

    monkeypatch.setattr(
        "kanbus.beads_write.remove_beads_dependency",
        lambda *_a: (_ for _ in ()).throw(cli.BeadsWriteError("beads remove fail")),
    )
    result_remove_beads_fail = _run(
        ["dep", "kanbus-1", "remove", "blocked-by", "kanbus-2"]
    )
    assert result_remove_beads_fail.exit_code != 0
    assert "beads remove fail" in result_remove_beads_fail.output

    monkeypatch.setattr(
        "kanbus.beads_write.add_beads_dependency",
        lambda *_a: (_ for _ in ()).throw(cli.BeadsWriteError("beads add fail")),
    )
    result_add_beads_fail = _run(["dep", "kanbus-1", "blocked-by", "kanbus-2"])
    assert result_add_beads_fail.exit_code != 0
    assert "beads add fail" in result_add_beads_fail.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ProjectMarkerError("project not initialized")),
    )
    removed: list[tuple[str, str, str]] = []
    monkeypatch.setattr(cli, "remove_dependency", lambda _r, i, t, d: removed.append((i, t, d)))

    result_remove = _run(["dep", "kanbus-1", "remove", "blocked-by", "kanbus-2"])
    assert result_remove.exit_code == 0
    assert removed == [("kanbus-1", "kanbus-2", "blocked-by")]

    monkeypatch.setattr(
        cli,
        "remove_dependency",
        lambda *_a: (_ for _ in ()).throw(DependencyError("dep remove fail")),
    )
    result_remove_fail = _run(["dep", "kanbus-1", "remove", "blocked-by", "kanbus-2"])
    assert result_remove_fail.exit_code != 0
    assert "dep remove fail" in result_remove_fail.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ProjectMarkerError("pm fail")),
    )
    monkeypatch.setattr(
        cli,
        "add_dependency",
        lambda *_a: (_ for _ in ()).throw(DependencyError("dep add fail")),
    )
    result_add_fail = _run(["dep", "kanbus-1", "blocked-by", "kanbus-2"])
    assert result_add_fail.exit_code != 0
    assert "dep add fail" in result_add_fail.output

    assert calls


def test_ready_command_success_and_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)
    monkeypatch.setattr(cli, "_resolve_beads_root", lambda _cwd: tmp_path / "repo")
    monkeypatch.setattr(cli, "_run_lifecycle_hooks_for_context", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "list_ready_issues",
        lambda *_a, **_k: [
            build_issue("kanbus-1"),
            build_issue("kanbus-2", custom={"project_path": "project-b"}),
        ],
    )

    result = _run(["--beads", "ready", "--local-only"])
    assert result.exit_code == 0
    assert "kanbus-1" in result.output
    assert "project-b kanbus-2" in result.output

    monkeypatch.setattr(
        cli,
        "list_ready_issues",
        lambda *_a, **_k: (_ for _ in ()).throw(DependencyError("ready fail")),
    )
    result_fail = _run(["ready"])
    assert result_fail.exit_code != 0
    assert "ready fail" in result_fail.output


def test_doctor_migrate_and_daemon_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    monkeypatch.setattr(cli, "run_doctor", lambda _r: SimpleNamespace(project_dir="/tmp/project"))
    assert "ok /tmp/project" in _run(["doctor"]).output

    monkeypatch.setattr(
        cli,
        "run_doctor",
        lambda _r: (_ for _ in ()).throw(DoctorError("doctor fail")),
    )
    result_doctor_fail = _run(["doctor"])
    assert result_doctor_fail.exit_code != 0

    monkeypatch.setattr(cli, "migrate_from_beads", lambda _r: SimpleNamespace(issue_count=5))
    assert "migrated 5 issues" in _run(["migrate"]).output

    monkeypatch.setattr(
        cli,
        "migrate_from_beads",
        lambda _r: (_ for _ in ()).throw(MigrationError("migrate fail")),
    )
    result_migrate_fail = _run(["migrate"])
    assert result_migrate_fail.exit_code != 0

    monkeypatch.setattr(cli, "request_status", lambda _r: {"ok": True})
    result_status = _run(["daemon-status"])
    assert result_status.exit_code == 0
    assert '"ok": true' in result_status.output

    monkeypatch.setattr(
        cli,
        "request_status",
        lambda _r: (_ for _ in ()).throw(ProjectMarkerError("project not initialized")),
    )
    result_status_pm = _run(["daemon-status"])
    assert result_status_pm.exit_code != 0

    monkeypatch.setattr(
        cli,
        "request_status",
        lambda _r: (_ for _ in ()).throw(DaemonClientError("daemon fail")),
    )
    result_status_fail = _run(["daemon-status"])
    assert result_status_fail.exit_code != 0

    monkeypatch.setattr(cli, "request_shutdown", lambda _r: {"stopped": True})
    result_stop = _run(["daemon-stop"])
    assert result_stop.exit_code == 0
    assert '"stopped": true' in result_stop.output

    monkeypatch.setattr(
        cli,
        "request_shutdown",
        lambda _r: (_ for _ in ()).throw(ProjectMarkerError("multiple projects found")),
    )
    result_stop_pm = _run(["daemon-stop"])
    assert result_stop_pm.exit_code != 0

    monkeypatch.setattr(
        cli,
        "request_shutdown",
        lambda _r: (_ for _ in ()).throw(DaemonClientError("stop fail")),
    )
    result_stop_fail = _run(["daemon-stop"])
    assert result_stop_fail.exit_code != 0


def test_gossip_overlay_and_project_marker_format(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    monkeypatch.setattr(cli, "run_gossip_broker", lambda *_a: None)
    assert _run(["gossip", "broker"]).exit_code == 0

    monkeypatch.setattr(
        cli,
        "run_gossip_broker",
        lambda *_a: (_ for _ in ()).throw(GossipError("broker fail")),
    )
    assert _run(["gossip", "broker"]).exit_code != 0

    monkeypatch.setattr(cli, "run_gossip_watch", lambda *_a: None)
    assert _run(["gossip", "watch", "--print"]).exit_code == 0

    monkeypatch.setattr(
        cli,
        "run_gossip_watch",
        lambda *_a: (_ for _ in ()).throw(GossipError("watch fail")),
    )
    assert _run(["gossip", "watch"]).exit_code != 0

    monkeypatch.setattr(cli, "gc_overlay_for_projects", lambda *_a: 2)
    result_gc = _run(["overlay", "gc", "--all"])
    assert result_gc.exit_code == 0
    assert "overlay gc complete (2 project(s))" in result_gc.output

    monkeypatch.setattr(
        cli,
        "gc_overlay_for_projects",
        lambda *_a: (_ for _ in ()).throw(ValueError("gc fail")),
    )
    assert _run(["overlay", "gc"]).exit_code != 0

    monkeypatch.setattr(
        cli,
        "reconcile_overlay_for_projects",
        lambda *_a, **_k: OverlayReconcileStats(
            projects=1,
            issues_scanned=2,
            issues_updated=3,
            issues_removed=4,
            fields_pruned=5,
        ),
    )
    result_reconcile = _run(["overlay", "reconcile", "--dry-run"])
    assert result_reconcile.exit_code == 0
    assert "projects=1" in result_reconcile.output

    monkeypatch.setattr(
        cli,
        "reconcile_overlay_for_projects",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("reconcile fail")),
    )
    assert _run(["overlay", "reconcile"]).exit_code != 0

    monkeypatch.setattr(cli, "install_overlay_hooks", lambda *_a: None)
    assert _run(["overlay", "install-hooks"]).exit_code == 0

    monkeypatch.setattr(
        cli,
        "install_overlay_hooks",
        lambda *_a: (_ for _ in ()).throw(RuntimeError("install fail")),
    )
    assert _run(["overlay", "install-hooks"]).exit_code != 0

    assert "single project/ folder" in cli._format_project_marker_error(
        ProjectMarkerError("multiple projects found")
    )
    assert 'Run "kanbus init"' in cli._format_project_marker_error(
        ProjectMarkerError("project not initialized")
    )
    assert cli._format_project_marker_error(ProjectMarkerError("other")) == "other"


def test_snyk_and_jira_pull_and_aliases(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    monkeypatch.setattr(
        cli,
        "get_configuration_path",
        lambda _r: (_ for _ in ()).throw(ProjectMarkerError("project not initialized")),
    )
    assert _run(["snyk", "pull"]).exit_code != 0

    monkeypatch.setattr(cli, "get_configuration_path", lambda _r: tmp_path / ".kanbus.yml")
    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ConfigurationError("cfg fail")),
    )
    result_snyk_cfg = _run(["snyk", "pull"])
    assert result_snyk_cfg.exit_code != 0
    assert "cfg fail" in result_snyk_cfg.output

    cfg_no_snyk = build_project_configuration().model_copy(update={"snyk": None})
    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: cfg_no_snyk)
    result_no_snyk = _run(["snyk", "pull"])
    assert result_no_snyk.exit_code != 0
    assert "no snyk configuration" in result_no_snyk.output

    cfg_with_snyk = build_project_configuration().model_copy(
        update={
            "snyk": SnykConfiguration(
                org_id="org",
                min_severity="low",
                parent_epic=None,
                repo=None,
            )
        }
    )
    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: cfg_with_snyk)
    monkeypatch.setattr(
        "kanbus.snyk_sync.pull_from_snyk",
        lambda *_a, **_k: SnykPullResult(pulled=1, updated=2, skipped=3),
    )
    result_snyk = _run(["snyk", "pull", "--dry-run", "--min-severity", "high"])
    assert result_snyk.exit_code == 0
    assert "Dry run" in result_snyk.output
    assert "pulled 1 new, updated 2 existing, skipped 3 duplicates" in result_snyk.output

    monkeypatch.setattr(
        "kanbus.snyk_sync.pull_from_snyk",
        lambda *_a, **_k: (_ for _ in ()).throw(SnykSyncError("snyk fail")),
    )
    assert _run(["snyk", "pull"]).exit_code != 0

    cfg_no_jira = cfg_with_snyk.model_copy(update={"jira": None})
    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: cfg_no_jira)
    result_no_jira = _run(["jira", "pull"])
    assert result_no_jira.exit_code != 0
    assert "no jira configuration" in result_no_jira.output

    monkeypatch.setattr(
        cli,
        "load_project_configuration",
        lambda _p: (_ for _ in ()).throw(ConfigurationError("jira cfg fail")),
    )
    result_jira_cfg = _run(["jira", "pull"])
    assert result_jira_cfg.exit_code != 0
    assert "jira cfg fail" in result_jira_cfg.output

    cfg_bad_sync = cfg_with_snyk.model_copy(
        update={
            "jira": JiraConfiguration(
                url="https://jira.example.com",
                project_key="KAN",
                sync_direction="push",
                type_mappings={},
                field_mappings={},
            )
        }
    )
    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: cfg_bad_sync)
    result_bad_sync = _run(["jira", "pull"])
    assert result_bad_sync.exit_code != 0
    assert "sync_direction" in result_bad_sync.output

    cfg_jira = cfg_with_snyk.model_copy(
        update={
            "jira": JiraConfiguration(
                url="https://jira.example.com",
                project_key="KAN",
                sync_direction="pull",
                type_mappings={},
                field_mappings={},
            )
        }
    )
    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: cfg_jira)
    monkeypatch.setattr(
        "kanbus.jira_sync.pull_from_jira",
        lambda *_a, **_k: SimpleNamespace(pulled=2, updated=1),
    )
    result_jira = _run(["jira", "pull", "--dry-run"])
    assert result_jira.exit_code == 0
    assert "Dry run" in result_jira.output
    assert "pulled 2 new, updated 1 existing" in result_jira.output

    monkeypatch.setattr(
        "kanbus.jira_sync.pull_from_jira",
        lambda *_a, **_k: (_ for _ in ()).throw(JiraSyncError("jira fail")),
    )
    assert _run(["jira", "pull"]).exit_code != 0

    invoked: list[dict] = []
    monkeypatch.setattr(cli, "list_command", lambda **kwargs: invoked.append(kwargs))
    assert _run(["issues"]).exit_code == 0
    assert _run(["epics"]).exit_code == 0
    assert _run(["tasks"]).exit_code == 0
    assert _run(["stories"]).exit_code == 0
    assert _run(["bugs"]).exit_code == 0
    assert invoked == [
        {},
        {"issue_type": "epic"},
        {"issue_type": "task"},
        {"issue_type": "story"},
        {"issue_type": "bug"},
    ]
