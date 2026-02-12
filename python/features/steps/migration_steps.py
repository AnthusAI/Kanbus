"""Behave steps for migration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from behave import given, then, when

from features.steps.shared import ensure_git_repository, load_project_directory, run_cli
from taskulus.migration import MigrationError, migrate_from_beads


def _fixture_beads_dir() -> Path:
    return (
        Path(__file__).resolve().parents[3]
        / "specs"
        / "fixtures"
        / "beads_repo"
        / ".beads"
    )


@given("a git repository with a .beads issues database")
def given_repo_with_beads(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    target_beads = repository_path / ".beads"
    shutil.copytree(_fixture_beads_dir(), target_beads)
    context.working_directory = repository_path


@given("a git repository without a .beads directory")
def given_repo_without_beads(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    context.working_directory = repository_path


@given("a git repository with an empty .beads directory")
def given_repo_empty_beads(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    (repository_path / ".beads").mkdir()
    context.working_directory = repository_path


@given("a git repository with a .beads issues database containing blank lines")
def given_repo_with_blank_lines(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    beads_dir = repository_path / ".beads"
    beads_dir.mkdir()
    record = {
        "id": "tsk-001",
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": [],
    }
    lines = "\n".join([json.dumps(record), "", json.dumps({**record, "id": "tsk-002"})])
    (beads_dir / "issues.jsonl").write_text(lines, encoding="utf-8")
    context.working_directory = repository_path


@given("a git repository with Beads metadata and dependencies")
def given_repo_with_metadata_dependencies(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    beads_dir = repository_path / ".beads"
    beads_dir.mkdir()
    base = {
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": [],
    }
    parent = {**base, "id": "tsk-parent"}
    child = {
        **base,
        "id": "tsk-child",
        "dependencies": [{"type": "blocked-by", "depends_on_id": "tsk-parent"}],
        "notes": "Notes",
        "acceptance_criteria": "Criteria",
        "close_reason": "Done",
        "owner": "dev@example.com",
    }
    lines = "\n".join([json.dumps(parent), json.dumps(child)])
    (beads_dir / "issues.jsonl").write_text(lines, encoding="utf-8")
    context.working_directory = repository_path


@given("a Taskulus project already exists")
def given_taskulus_project_exists(context: object) -> None:
    repository_path = context.working_directory
    (repository_path / "project" / "issues").mkdir(parents=True, exist_ok=True)


@when('I run "tsk migrate"')
def when_run_migrate(context: object) -> None:
    run_cli(context, "tsk migrate")


@when("I validate migration error cases")
def when_validate_migration_errors(context: object) -> None:
    errors = []

    def run_case(records: list[dict], label: str) -> None:
        repo = Path(context.temp_dir) / f"case-{label}"
        repo.mkdir(parents=True, exist_ok=True)
        ensure_git_repository(repo)
        beads_dir = repo / ".beads"
        beads_dir.mkdir()
        lines = "\n".join(json.dumps(record) for record in records)
        (beads_dir / "issues.jsonl").write_text(lines, encoding="utf-8")
        try:
            migrate_from_beads(repo)
        except MigrationError as error:
            errors.append(str(error))
            return
        errors.append("expected error not raised")

    valid_base = {
        "id": "tsk-001",
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "closed_at": None,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": [],
    }

    run_case([{"title": "Missing id"}], "missing-id")
    run_case([{**valid_base, "title": ""}], "missing-title")
    run_case([{**valid_base, "issue_type": ""}], "missing-type")
    run_case([{**valid_base, "status": ""}], "missing-status")
    record_without_priority = valid_base.copy()
    record_without_priority.pop("priority")
    run_case([record_without_priority], "missing-priority-field")
    run_case([{**valid_base, "priority": None}], "missing-priority")
    run_case([{**valid_base, "priority": 99}], "invalid-priority")
    run_case([{**valid_base, "issue_type": "unknown"}], "unknown-type")
    run_case([{**valid_base, "status": "invalid"}], "invalid-status")
    run_case(
        [
            {
                **valid_base,
                "dependencies": [{"type": "", "depends_on_id": ""}],
            }
        ],
        "invalid-dependency",
    )
    run_case(
        [
            {
                **valid_base,
                "dependencies": [{"type": "blocked-by", "depends_on_id": "tsk-missing"}],
            }
        ],
        "missing-dependency",
    )
    run_case(
        [
            {
                **valid_base,
                "id": "tsk-child",
                "dependencies": [
                    {"type": "parent-child", "depends_on_id": "tsk-parent"},
                    {"type": "parent-child", "depends_on_id": "tsk-parent-2"},
                ],
            },
            {
                **valid_base,
                "id": "tsk-parent",
            },
            {
                **valid_base,
                "id": "tsk-parent-2",
            },
        ],
        "multiple-parents",
    )
    run_case(
        [
            {
                **valid_base,
                "id": "tsk-child",
                "dependencies": [{"type": "parent-child", "depends_on_id": "tsk-parent"}],
            },
            {
                "id": "tsk-parent",
                "title": "Parent",
                "status": "open",
                "priority": 2,
                "created_at": "2026-02-11T00:00:00Z",
                "updated_at": "2026-02-11T00:00:00Z",
            },
        ],
        "parent-issue-type-missing",
    )
    run_case(
        [{**valid_base, "comments": [{"author": "", "text": "bad", "created_at": "2026-02-11T00:00:00Z"}]}],
        "invalid-comment",
    )
    run_case(
        [{**valid_base, "comments": [{"author": "dev", "text": "ok"}]}],
        "comment-created-missing",
    )
    run_case(
        [{**valid_base, "comments": [{"author": "dev", "text": "ok", "created_at": 123}]}],
        "comment-created-not-string",
    )
    run_case(
        [{**valid_base, "comments": [{"author": "dev", "text": "ok", "created_at": "bad"}]}],
        "comment-created-invalid",
    )
    run_case(
        [{**valid_base, "comments": [{"author": "dev", "text": "ok", "created_at": ""}]}],
        "comment-created-empty",
    )
    run_case([{**valid_base, "created_at": None}], "created-missing")
    run_case([{**valid_base, "created_at": ""}], "created-empty")
    run_case([{**valid_base, "created_at": 123}], "created-not-string")
    run_case([{**valid_base, "created_at": "invalid"}], "created-invalid")
    context.migration_errors = errors


@then("a Taskulus project should be initialized")
def then_taskulus_initialized(context: object) -> None:
    project_dir = load_project_directory(context)
    assert project_dir.is_dir()


@then("all Beads issues should be converted to Taskulus issues")
def then_beads_converted(context: object) -> None:
    issues_path = context.working_directory / ".beads" / "issues.jsonl"
    lines = [
        line
        for line in issues_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    project_dir = load_project_directory(context)
    issue_files = list((project_dir / "issues").glob("*.json"))
    assert len(issue_files) == len(lines)


@then("migrated issues should include metadata and dependencies")
def then_migration_includes_metadata(context: object) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / "tsk-child.json"
    payload = json.loads(issue_path.read_text(encoding="utf-8"))
    custom = payload.get("custom", {})
    assert custom.get("beads_notes") == "Notes"
    assert custom.get("beads_acceptance_criteria") == "Criteria"
    assert custom.get("beads_close_reason") == "Done"
    assert custom.get("beads_owner") == "dev@example.com"
    dependencies = payload.get("dependencies", [])
    assert any(
        item.get("target") == "tsk-parent" and item.get("type") == "blocked-by"
        for item in dependencies
    )


@then('migration errors should include "{message}"')
def then_migration_errors_include(context: object, message: str) -> None:
    errors = getattr(context, "migration_errors", [])
    assert message in errors
