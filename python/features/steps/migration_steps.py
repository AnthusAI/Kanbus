"""Behave steps for migration."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from behave import given, then, when

from features.steps.shared import ensure_git_repository, load_project_directory, run_cli
from kanbus.migration import MigrationError, migrate_from_beads


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


@given("a git repository with an empty issues.jsonl file")
def given_repo_with_empty_issues_jsonl(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    beads_dir = repository_path / ".beads"
    beads_dir.mkdir()
    (beads_dir / "issues.jsonl").write_text("", encoding="utf-8")
    context.working_directory = repository_path


@given("a git repository with a .beads issues database containing blank lines")
def given_repo_with_blank_lines(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    beads_dir = repository_path / ".beads"
    beads_dir.mkdir()
    record = {
        "id": "kanbus-001",
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": [],
    }
    lines = "\n".join([json.dumps(record), "", json.dumps({**record, "id": "kanbus-002"})])
    (beads_dir / "issues.jsonl").write_text(lines, encoding="utf-8")
    context.working_directory = repository_path


@given("a git repository with a .beads issues database containing an invalid id")
def given_repo_with_invalid_beads_id(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    beads_dir = repository_path / ".beads"
    beads_dir.mkdir()
    record = {
        "id": "invalidid",
        "title": "Title",
        "issue_type": "task",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": [],
    }
    (beads_dir / "issues.jsonl").write_text(json.dumps(record), encoding="utf-8")
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
    parent = {**base, "id": "kanbus-parent"}
    child = {
        **base,
        "id": "kanbus-child",
        "dependencies": [{"type": "blocked-by", "depends_on_id": "kanbus-parent"}],
        "notes": "Notes",
        "acceptance_criteria": "Criteria",
        "close_reason": "Done",
        "owner": "dev@example.com",
    }
    lines = "\n".join([json.dumps(parent), json.dumps(child)])
    (beads_dir / "issues.jsonl").write_text(lines, encoding="utf-8")
    context.working_directory = repository_path


@given("a git repository with a Beads feature issue")
def given_repo_with_feature_issue(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    beads_dir = repository_path / ".beads"
    beads_dir.mkdir()
    record = {
        "id": "bdx-feature",
        "title": "Feature issue",
        "issue_type": "feature",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": [],
    }
    (beads_dir / "issues.jsonl").write_text(json.dumps(record), encoding="utf-8")
    context.working_directory = repository_path


@given("a git repository with Beads epic parent and child")
def given_repo_with_epic_parent_child(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    beads_dir = repository_path / ".beads"
    beads_dir.mkdir()
    parent_record = {
        "id": "bdx-parent",
        "title": "Parent epic",
        "issue_type": "epic",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [],
        "comments": [],
    }
    child_record = {
        "id": "bdx-child",
        "title": "Child epic",
        "issue_type": "epic",
        "status": "open",
        "priority": 2,
        "created_at": "2026-02-11T00:00:00Z",
        "updated_at": "2026-02-11T00:00:00Z",
        "dependencies": [
            {
                "issue_id": "bdx-child",
                "depends_on_id": "bdx-parent",
                "type": "parent-child",
                "created_at": "2026-02-11T00:00:00Z",
                "created_by": "dev@example.com",
            }
        ],
        "comments": [],
    }
    lines = "\n".join(json.dumps(record) for record in [parent_record, child_record])
    (beads_dir / "issues.jsonl").write_text(lines, encoding="utf-8")
    context.working_directory = repository_path


@given("a git repository with Beads issues containing fractional timestamps")
def given_repo_with_fractional_timestamps(context: object) -> None:
    repository_path = Path(context.temp_dir) / "repo"
    repository_path.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(repository_path)
    beads_dir = repository_path / ".beads"
    beads_dir.mkdir()
    records = [
        {
            "id": "bdx-frac-short",
            "title": "Short fractional",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-11T00:00:00.1+00:00",
            "updated_at": "2026-02-11T00:00:00.1+00:00",
            "dependencies": [],
            "comments": [],
        },
        {
            "id": "bdx-frac-long",
            "title": "Long fractional",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-11T00:00:00.1234567+00:00",
            "updated_at": "2026-02-11T00:00:00.1234567+00:00",
            "dependencies": [],
            "comments": [],
        },
        {
            "id": "bdx-frac-nozone",
            "title": "No zone",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-11T00:00:00.123",
            "updated_at": "2026-02-11T00:00:00.123",
            "dependencies": [],
            "comments": [],
        },
        {
            "id": "bdx-frac-negative",
            "title": "Negative offset",
            "issue_type": "task",
            "status": "open",
            "priority": 2,
            "created_at": "2026-02-11T00:00:00.123456-05:00",
            "updated_at": "2026-02-11T00:00:00.123456-05:00",
            "dependencies": [],
            "comments": [],
        },
    ]
    lines = "\n".join(json.dumps(record) for record in records)
    (beads_dir / "issues.jsonl").write_text(lines, encoding="utf-8")
    context.working_directory = repository_path


@given("a Kanbus project already exists")
def given_kanbus_project_exists(context: object) -> None:
    repository_path = context.working_directory
    (repository_path / "project" / "issues").mkdir(parents=True, exist_ok=True)


@when('I run "kanbus migrate"')
def when_run_migrate(context: object) -> None:
    run_cli(context, "kanbus migrate")


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
        "id": "kanbus-001",
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
                "dependencies": [
                    {"type": "blocked-by", "depends_on_id": "kanbus-missing"}
                ],
            }
        ],
        "missing-dependency",
    )
    run_case(
        [
            {
                **valid_base,
                "id": "kanbus-child",
                "dependencies": [
                    {"type": "parent-child", "depends_on_id": "kanbus-parent"},
                    {"type": "parent-child", "depends_on_id": "kanbus-parent-2"},
                ],
            },
            {
                **valid_base,
                "id": "kanbus-parent",
            },
            {
                **valid_base,
                "id": "kanbus-parent-2",
            },
        ],
        "multiple-parents",
    )
    run_case(
        [
            {
                **valid_base,
                "id": "kanbus-child",
                "dependencies": [
                    {"type": "parent-child", "depends_on_id": "kanbus-parent"}
                ],
            },
            {
                "id": "kanbus-parent",
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
        [
            {
                **valid_base,
                "comments": [
                    {"author": "", "text": "bad", "created_at": "2026-02-11T00:00:00Z"}
                ],
            }
        ],
        "invalid-comment",
    )
    run_case(
        [{**valid_base, "comments": [{"author": "dev", "text": "ok"}]}],
        "comment-created-missing",
    )
    run_case(
        [
            {
                **valid_base,
                "comments": [{"author": "dev", "text": "ok", "created_at": 123}],
            }
        ],
        "comment-created-not-string",
    )
    run_case(
        [
            {
                **valid_base,
                "comments": [{"author": "dev", "text": "ok", "created_at": "bad"}],
            }
        ],
        "comment-created-invalid",
    )
    run_case(
        [
            {
                **valid_base,
                "comments": [{"author": "dev", "text": "ok", "created_at": ""}],
            }
        ],
        "comment-created-empty",
    )
    run_case([{**valid_base, "created_at": None}], "created-missing")
    run_case([{**valid_base, "created_at": ""}], "created-empty")
    run_case([{**valid_base, "created_at": 123}], "created-not-string")
    run_case([{**valid_base, "created_at": "invalid"}], "created-invalid")
    run_case(
        [{**valid_base, "created_at": "2026-02-11T00:00:00.bad+00:00"}],
        "created-invalid-fractional",
    )
    run_case(
        [{**valid_base, "created_at": "2026-02-11T00:00:00.bad-00:00"}],
        "created-invalid-negative",
    )
    run_case(
        [{**valid_base, "created_at": "2026-02-11T00:00:00.123+00:00-00"}],
        "created-invalid-mixed-offset",
    )
    context.migration_errors = errors


@then("a Kanbus project should be initialized")
def then_kanbus_initialized(context: object) -> None:
    project_dir = load_project_directory(context)
    assert project_dir.is_dir()


@then("all Beads issues should be converted to Kanbus issues")
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
    issue_path = project_dir / "issues" / "kanbus-child.json"
    payload = json.loads(issue_path.read_text(encoding="utf-8"))
    custom = payload.get("custom", {})
    assert custom.get("beads_notes") == "Notes"
    assert custom.get("beads_acceptance_criteria") == "Criteria"
    assert custom.get("beads_close_reason") == "Done"
    assert custom.get("beads_owner") == "dev@example.com"
    dependencies = payload.get("dependencies", [])
    assert any(
        item.get("target") == "kanbus-parent" and item.get("type") == "blocked-by"
        for item in dependencies
    )


@then('migrated issue "{identifier}" should have type "{issue_type}"')
def then_migrated_issue_type(context: object, identifier: str, issue_type: str) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / f"{identifier}.json"
    payload = json.loads(issue_path.read_text(encoding="utf-8"))
    assert payload.get("type") == issue_type


@then('migrated issue "{identifier}" should have parent "{parent}"')
def then_migrated_issue_parent(context: object, identifier: str, parent: str) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / f"{identifier}.json"
    payload = json.loads(issue_path.read_text(encoding="utf-8"))
    assert payload.get("parent") == parent


@then('migrated issue "{identifier}" should preserve beads issue type "{issue_type}"')
def then_migrated_issue_preserves_type(
    context: object, identifier: str, issue_type: str
) -> None:
    project_dir = load_project_directory(context)
    issue_path = project_dir / "issues" / f"{identifier}.json"
    payload = json.loads(issue_path.read_text(encoding="utf-8"))
    custom = payload.get("custom", {})
    assert custom.get("beads_issue_type") == issue_type


@then('migration errors should include "{message}"')
def then_migration_errors_include(context: object, message: str) -> None:
    errors = getattr(context, "migration_errors", [])
    assert message in errors
