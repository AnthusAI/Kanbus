from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from kanbus import cli
from test_helpers import build_project_configuration


def _run(args: list[str]) -> object:
    return CliRunner().invoke(cli.cli, args)


def test_hooks_list_and_validate_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    monkeypatch.setattr(cli, "list_hooks", lambda _root: [])
    result_empty = _run(["hooks", "list"])
    assert result_empty.exit_code == 0
    assert "No hooks configured." in result_empty.output

    monkeypatch.setattr(
        cli,
        "list_hooks",
        lambda _root: [
            {
                "source": "external",
                "phase": "before",
                "event": "issue.create",
                "id": "h1",
                "command": "echo ok",
                "blocking": True,
                "timeout_ms": None,
            }
        ],
    )
    result_rows = _run(["hooks", "list"])
    assert result_rows.exit_code == 0
    assert "[external] before issue.create h1" in result_rows.output
    assert "timeout_ms: default" in result_rows.output

    monkeypatch.setattr(cli, "validate_hooks", lambda _root: ["bad hook"])  # type: ignore[arg-type]
    result_invalid = _run(["hooks", "validate"])
    assert result_invalid.exit_code != 0
    assert "Found 1 hook validation issue" in result_invalid.output

    monkeypatch.setattr(cli, "validate_hooks", lambda _root: [])
    result_valid = _run(["hooks", "validate"])
    assert result_valid.exit_code == 0
    assert "Hook configuration is valid." in result_valid.output


def test_wiki_render_and_list_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    monkeypatch.setattr(cli, "render_wiki_page", lambda _req: "rendered")
    result_render = _run(["wiki", "render", "project/wiki/page.md"])
    assert result_render.exit_code == 0
    assert "rendered" in result_render.output

    monkeypatch.setattr(
        cli,
        "render_wiki_page",
        lambda _req: (_ for _ in ()).throw(cli.WikiError("wiki fail")),
    )
    result_render_fail = _run(["wiki", "render", "project/wiki/page.md"])
    assert result_render_fail.exit_code != 0
    assert "wiki fail" in result_render_fail.output

    monkeypatch.setattr(cli, "list_wiki_pages", lambda _root: ["project/wiki/a.md", "project/wiki/b.md"])
    result_list = _run(["wiki", "list"])
    assert result_list.exit_code == 0
    assert "project/wiki/a.md" in result_list.output
    assert "project/wiki/b.md" in result_list.output

    monkeypatch.setattr(
        cli,
        "list_wiki_pages",
        lambda _root: (_ for _ in ()).throw(cli.WikiError("list fail")),
    )
    result_list_fail = _run(["wiki", "list"])
    assert result_list_fail.exit_code != 0
    assert "list fail" in result_list_fail.output


def test_edit_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    monkeypatch.setattr(cli, "edit_view", lambda _root, _path, _rng: "view")
    assert _run(["edit", "view", "README.md", "--view-range", "1", "10"]).exit_code == 0

    monkeypatch.setattr(cli, "edit_str_replace", lambda _root, _path, _o, _n: "replace")
    assert _run(["edit", "str-replace", "README.md", "--old-str", "a", "--new-str", "b"]).exit_code == 0

    monkeypatch.setattr(cli, "edit_create", lambda _root, _path, _text: "create")
    assert _run(["edit", "create", "x.txt", "--file-text", "x"]).exit_code == 0

    monkeypatch.setattr(cli, "edit_insert", lambda _root, _path, _line, _text: "insert")
    assert _run(["edit", "insert", "x.txt", "--insert-line", "1", "--insert-text", "x"]).exit_code == 0

    monkeypatch.setattr(
        cli,
        "edit_view",
        lambda *_a: (_ for _ in ()).throw(cli.TextEditorError("view fail")),
    )
    result_fail = _run(["edit", "view", "README.md"])
    assert result_fail.exit_code != 0
    assert "view fail" in result_fail.output


def test_policy_check_command_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    lookup = SimpleNamespace(issue=SimpleNamespace(identifier="kanbus-1"), project_dir=tmp_path / "project")

    monkeypatch.setattr("kanbus.issue_lookup.load_issue_from_project", lambda _root, _id: lookup)
    monkeypatch.setattr("kanbus.config_loader.load_project_configuration", lambda _p: SimpleNamespace())
    monkeypatch.setattr("kanbus.project.get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")

    policies = lookup.project_dir / "policies"
    policies.mkdir(parents=True)

    monkeypatch.setattr("kanbus.policy_loader.load_policies", lambda _p: [])
    result_no_files = _run(["policy", "check", "kanbus-1"])
    assert result_no_files.exit_code == 0
    assert "No policy files found" in result_no_files.output

    monkeypatch.setattr("kanbus.policy_loader.load_policies", lambda _p: [("p.feature", object())])
    monkeypatch.setattr("kanbus.issue_listing.load_issues_from_directory", lambda _d: [])
    monkeypatch.setattr("kanbus.policy_evaluator.evaluate_policies_with_options", lambda *_a, **_k: [])

    result_ok = _run(["policy", "check", "kanbus-1"])
    assert result_ok.exit_code == 0
    assert "All policies passed for kanbus-1" in result_ok.output

    monkeypatch.setattr(
        "kanbus.policy_evaluator.evaluate_policies_with_options",
        lambda *_a, **_k: [RuntimeError("v1")],
    )
    result_violation = _run(["policy", "check", "kanbus-1"])
    assert result_violation.exit_code != 0
    assert "policy violation" in result_violation.output.lower() or "Found 1 policy violation" in result_violation.output

    monkeypatch.setattr(
        "kanbus.issue_lookup.load_issue_from_project",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("lookup fail")),
    )
    result_lookup_fail = _run(["policy", "check", "kanbus-1"])
    assert result_lookup_fail.exit_code != 0
    assert "lookup fail" in result_lookup_fail.output


def test_policy_guide_list_steps_validate_commands(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli.Path, "cwd", lambda: tmp_path)

    lookup = SimpleNamespace(issue=SimpleNamespace(identifier="kanbus-1"), project_dir=tmp_path / "project")
    monkeypatch.setattr("kanbus.issue_lookup.load_issue_from_project", lambda _root, _id: lookup)

    report = SimpleNamespace(violations=[], guidance_items=[])
    monkeypatch.setattr("kanbus.policy_guidance.collect_guidance_for_issue", lambda **_k: report)
    monkeypatch.setattr("kanbus.policy_guidance.sorted_deduped_guidance_items", lambda items: items)

    result_none = _run(["policy", "guide", "kanbus-1"])
    assert result_none.exit_code == 0
    assert "No guidance for kanbus-1" in result_none.output

    report.guidance_items = [
        SimpleNamespace(severity=SimpleNamespace(value="warning"), message="warn", explanations=["exp"])
    ]
    result_guidance = _run(["policy", "guide", "kanbus-1"])
    assert result_guidance.exit_code == 0
    assert "GUIDANCE WARNING: warn" in result_guidance.output

    report.violations = [RuntimeError("bad policy")]
    result_validation = _run(["policy", "guide", "kanbus-1"])
    assert result_validation.exit_code != 0
    assert "validation issue" in result_validation.output.lower()

    monkeypatch.setattr(
        "kanbus.issue_lookup.load_issue_from_project",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("guide fail")),
    )
    result_guide_fail = _run(["policy", "guide", "kanbus-1"])
    assert result_guide_fail.exit_code != 0
    assert "guide fail" in result_guide_fail.output

    monkeypatch.setattr("kanbus.project.load_project_directory", lambda _r: tmp_path / "project")
    policies = tmp_path / "project" / "policies"
    policies.mkdir(parents=True, exist_ok=True)

    doc = SimpleNamespace(
        feature=SimpleNamespace(name="F", children=[SimpleNamespace(scenario=SimpleNamespace(name="S"))])
    )
    monkeypatch.setattr("kanbus.policy_loader.load_policies", lambda _p: [("p.feature", doc)])

    result_list = _run(["policy", "list"])
    assert result_list.exit_code == 0
    assert "p.feature" in result_list.output
    assert "Feature: F" in result_list.output
    assert "Scenario: S" in result_list.output

    monkeypatch.setattr("kanbus.policy_loader.load_policies", lambda _p: [])
    result_list_none = _run(["policy", "list"])
    assert result_list_none.exit_code == 0
    assert "No policy files found" in result_list_none.output

    monkeypatch.setattr(
        "kanbus.project.load_project_directory",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("list fail")),
    )
    result_list_fail = _run(["policy", "list"])
    assert result_list_fail.exit_code != 0
    assert "list fail" in result_list_fail.output

    steps = [
        SimpleNamespace(category=SimpleNamespace(value="Given"), description="D1", usage_pattern="P1"),
        SimpleNamespace(category=SimpleNamespace(value="Then"), description="D2", usage_pattern="P2"),
    ]
    monkeypatch.setattr("kanbus.policy_evaluator._get_step_registry", lambda: SimpleNamespace(steps=steps))

    result_steps = _run(["policy", "steps", "--category", "given", "--search", "d1"])
    assert result_steps.exit_code == 0
    assert "Given - D1" in result_steps.output

    result_steps_none = _run(["policy", "steps", "--category", "when"])
    assert result_steps_none.exit_code == 0
    assert "No matching steps found" in result_steps_none.output

    monkeypatch.setattr("kanbus.project.load_project_directory", lambda _r: tmp_path / "project")
    monkeypatch.setattr("kanbus.policy_loader.load_policies", lambda _p: [("p.feature", doc)])
    monkeypatch.setattr(cli, "load_project_configuration", lambda _p: build_project_configuration())
    monkeypatch.setattr(cli, "get_configuration_path", lambda _p: tmp_path / ".kanbus.yml")
    monkeypatch.setattr("kanbus.policy_evaluator.validate_policy_documents", lambda *_a: [])
    result_validate_ok = _run(["policy", "validate"])
    assert result_validate_ok.exit_code == 0
    assert "All 1 policy files are valid" in result_validate_ok.output

    monkeypatch.setattr("kanbus.policy_evaluator.validate_policy_documents", lambda *_a: [RuntimeError("v")])
    result_validate_fail = _run(["policy", "validate"])
    assert result_validate_fail.exit_code != 0
    assert "validation issue" in result_validate_fail.output.lower()
