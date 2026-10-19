"""Behave steps for virtual project scenarios."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from behave import given, then, when

from features.steps.shared import (
    build_issue,
    ensure_git_repository,
    load_project_directory,
    read_issue_file,
    run_cli,
    run_cli_with_input,
    write_issue_file,
)


@dataclass
class VirtualProjectPaths:
    label: str
    root: Path
    shared_dir: Path
    local_dir: Path
    events_dir: Path


@dataclass
class VirtualProjectState:
    root: Path
    current_label: str
    current_project_dir: Path
    current_local_dir: Path
    virtual_projects: Dict[str, VirtualProjectPaths]
    pending_interactive_command: Optional[str] = None
    issue_snapshots: Dict[Path, str] = field(default_factory=dict)


def _repo_root(context: object) -> Path:
    return Path(context.temp_dir) / "repo"


def _initialize_virtual_repo(context: object) -> VirtualProjectState:
    root = _repo_root(context)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(root)
    context.working_directory = root
    run_cli(context, "kanbus init")
    if context.result.exit_code != 0:
        raise AssertionError("failed to initialize project")
    _set_primary_configuration_value(root, "project_key", "kbs")
    current_project_dir = root / "project"
    current_local_dir = root / "project-local"
    (current_local_dir / "issues").mkdir(parents=True, exist_ok=True)
    (current_local_dir / "events").mkdir(parents=True, exist_ok=True)
    state = VirtualProjectState(
        root=root,
        current_label="kbs",
        current_project_dir=current_project_dir,
        current_local_dir=current_local_dir,
        virtual_projects={},
    )
    context.virtual_project_state = state
    return state


def _set_primary_configuration_value(root: Path, key: str, value: object) -> None:
    config_path = root / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    payload[key] = value
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _remember_issue_snapshot(
    state: VirtualProjectState, project_dir: Path, identifier: str
) -> None:
    issue_path = project_dir / "issues" / f"{identifier}.json"
    state.issue_snapshots[issue_path] = issue_path.read_text(encoding="utf-8")


def _assert_issue_changed_since_snapshot(
    state: VirtualProjectState, project_dir: Path
) -> None:
    changed = any(
        path.is_relative_to(project_dir)
        and path.exists()
        and path.read_text(encoding="utf-8") != original
        for path, original in state.issue_snapshots.items()
    )
    assert changed, f"no issue file under {project_dir} changed since it was created"


def _ensure_virtual_state(context: object) -> VirtualProjectState:
    state = getattr(context, "virtual_project_state", None)
    if state is None:
        state = _initialize_virtual_repo(context)
    return state


def _configure_virtual_projects(
    context: object, labels: List[str]
) -> VirtualProjectState:
    state = _ensure_virtual_state(context)
    for label in labels:
        if label in state.virtual_projects:
            continue
        root = state.root / "virtual" / label
        shared_dir = root / "project"
        local_dir = root / "project-local"
        events_dir = shared_dir / "events"
        (shared_dir / "issues").mkdir(parents=True, exist_ok=True)
        events_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "issues").mkdir(parents=True, exist_ok=True)
        (local_dir / "events").mkdir(parents=True, exist_ok=True)
        state.virtual_projects[label] = VirtualProjectPaths(
            label=label,
            root=root,
            shared_dir=shared_dir,
            local_dir=local_dir,
            events_dir=events_dir,
        )
    _write_virtual_projects_configuration(state)
    return state


def _create_issue(
    project_dir: Path,
    identifier: str,
    title: str,
    status: str = "open",
    issue_type: str = "task",
    priority: int = 2,
) -> None:
    issue = build_issue(identifier, title, issue_type, status, None, [])
    issue = issue.model_copy(update={"priority": priority})
    write_issue_file(project_dir, issue)


def _issue_project_label(state: VirtualProjectState, identifier: str) -> Optional[str]:
    if (state.current_project_dir / "issues" / f"{identifier}.json").exists():
        return state.current_label
    if (state.current_local_dir / "issues" / f"{identifier}.json").exists():
        return state.current_label
    for label, project in state.virtual_projects.items():
        if (project.shared_dir / "issues" / f"{identifier}.json").exists():
            return label
        if (project.local_dir / "issues" / f"{identifier}.json").exists():
            return label
    return None


def _adopt_existing_repository_for_virtual_projects(
    context: object,
) -> VirtualProjectState:
    root = Path(context.working_directory)
    current_project_dir = load_project_directory(context)
    current_local_dir = root / "project-local"
    current_local_dir.mkdir(parents=True, exist_ok=True)
    (current_local_dir / "issues").mkdir(parents=True, exist_ok=True)
    (current_local_dir / "events").mkdir(parents=True, exist_ok=True)
    state = VirtualProjectState(
        root=root,
        current_label="kbs",
        current_project_dir=current_project_dir,
        current_local_dir=current_local_dir,
        virtual_projects={},
    )
    context.virtual_project_state = state
    return state


def _write_virtual_projects_configuration(state: VirtualProjectState) -> None:
    config_path = state.root / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    virtual_projects = payload.get("virtual_projects") or {}
    for label, project in state.virtual_projects.items():
        if label in virtual_projects:
            continue
        virtual_projects[label] = {
            "path": str(project.shared_dir.relative_to(state.root))
        }
    payload["virtual_projects"] = virtual_projects
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given("a Kanbus project with virtual projects configured")
def given_project_with_virtual_projects(context: object) -> None:
    if getattr(context, "virtual_project_state", None) is None:
        if getattr(context, "working_directory", None) is not None:
            state = _adopt_existing_repository_for_virtual_projects(context)
        else:
            state = _ensure_virtual_state(context)
    else:
        state = _ensure_virtual_state(context)
    state = _configure_virtual_projects(context, ["alpha", "beta"])
    for issue_path in (state.current_project_dir / "issues").glob("*.json"):
        issue_path.unlink()
    for issue_path in (state.current_local_dir / "issues").glob("*.json"):
        issue_path.unlink()
    for project in state.virtual_projects.values():
        for issue_path in (project.shared_dir / "issues").glob("*.json"):
            issue_path.unlink()
        for issue_path in (project.local_dir / "issues").glob("*.json"):
            issue_path.unlink()


@given('virtual projects "{alpha}" and "{beta}" are configured')
def given_virtual_projects_alpha_beta(context: object, alpha: str, beta: str) -> None:
    _configure_virtual_projects(context, [alpha, beta])


@given('virtual project "{label}" has display name "{display_name}"')
def given_virtual_project_display_name(
    context: object, label: str, display_name: str
) -> None:
    state = _ensure_virtual_state(context)
    if label not in state.virtual_projects and label != state.current_label:
        _configure_virtual_projects(context, [label])
    config_path = state.root / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    virtual_projects = payload.setdefault("virtual_projects", {})
    if label in state.virtual_projects:
        project = state.virtual_projects[label]
        virtual_projects.setdefault(label, {})
        virtual_projects[label]["path"] = str(
            project.shared_dir.relative_to(state.root)
        )
    virtual_projects[label]["display_name"] = display_name
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given('congregation primary display name is "{display_name}"')
def given_congregation_primary_display_name(context: object, display_name: str) -> None:
    state = _ensure_virtual_state(context)
    config_path = state.root / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    payload["name"] = display_name
    config_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


@given('a Kanbus project with new_issue_project set to "{label}"')
def given_project_with_new_issue_project(context: object, label: str) -> None:
    state = _configure_virtual_projects(context, ["alpha", "beta"])
    _set_primary_configuration_value(state.root, "new_issue_project", label)


@when('I run "kanbus create Interactive task" interactively')
def when_run_interactive_create(context: object) -> None:
    state = _ensure_virtual_state(context)
    state.pending_interactive_command = "kanbus create Interactive task"


@when('I select "{label}" from the project prompt')
def when_select_project_from_prompt(context: object, label: str) -> None:
    state = _ensure_virtual_state(context)
    assert state.pending_interactive_command, "interactive command was not started"
    run_cli_with_input(context, state.pending_interactive_command, f"{label}\n")


@then('the project prompt should list "{label}"')
def then_prompt_should_list(context: object, label: str) -> None:
    state = _ensure_virtual_state(context)
    assert state.pending_interactive_command, "interactive command was not started"
    run_cli_with_input(context, state.pending_interactive_command, "")
    output = f"{context.result.stdout}{context.result.stderr}"
    assert label in output, f"project prompt output did not list {label}: {output}"


@then("an issue file should be created in the current project issues directory")
def then_issue_in_current_project(context: object) -> None:
    state = _ensure_virtual_state(context)
    issues = list((state.current_project_dir / "issues").glob("*.json"))
    assert issues


@then("no issue file should be created in any virtual project")
def then_no_issue_in_virtual_projects(context: object) -> None:
    state = _ensure_virtual_state(context)
    for project in state.virtual_projects.values():
        shared = list((project.shared_dir / "issues").glob("*.json"))
        local = list((project.local_dir / "issues").glob("*.json"))
        assert not shared, f"unexpected shared issues: {shared}"
        assert not local, f"unexpected local issues: {local}"


@then('an issue file should be created in the "{label}" project issues directory')
def then_issue_in_virtual_project(context: object, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    issues = list((project.shared_dir / "issues").glob("*.json"))
    assert issues


@then("a local issue file should be created in the current project local directory")
def then_local_issue_current(context: object) -> None:
    state = _ensure_virtual_state(context)
    issues = list((state.current_local_dir / "issues").glob("*.json"))
    assert issues


@then('a local issue file should be created in the "{label}" project local directory')
def then_local_issue_virtual(context: object, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    issues = list((project.local_dir / "issues").glob("*.json"))
    assert issues


@given('an issue "{identifier}" exists in virtual project "{label}"')
def given_issue_exists_virtual(context: object, identifier: str, label: str) -> None:
    state = _ensure_virtual_state(context)
    if label not in state.virtual_projects:
        state = _configure_virtual_projects(context, [label])
    project = state.virtual_projects[label]
    _create_issue(project.shared_dir, identifier, "Virtual issue")
    _remember_issue_snapshot(state, project.shared_dir, identifier)


@given('an issue "{identifier}" exists in the primary project')
def given_issue_exists_primary(context: object, identifier: str) -> None:
    state = _ensure_virtual_state(context)
    _create_issue(state.current_project_dir, identifier, "Primary issue")
    _remember_issue_snapshot(state, state.current_project_dir, identifier)


@given('a local issue "{identifier}" exists in virtual project "{label}"')
def given_local_issue_exists_virtual(
    context: object, identifier: str, label: str
) -> None:
    state = _ensure_virtual_state(context)
    if label not in state.virtual_projects:
        state = _configure_virtual_projects(context, [label])
    project = state.virtual_projects[label]
    _create_issue(project.local_dir, identifier, "Local virtual issue")


@then('the issue file in virtual project "{label}" should be updated')
def then_issue_file_updated_virtual(context: object, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    _assert_issue_changed_since_snapshot(state, project.shared_dir)


@then("the issue file in the primary project should be updated")
def then_issue_file_updated_primary(context: object) -> None:
    state = _ensure_virtual_state(context)
    _assert_issue_changed_since_snapshot(state, state.current_project_dir)


@then("no issue file should be created in the current project")
def then_no_issue_created_current(context: object) -> None:
    state = _ensure_virtual_state(context)
    issues = list((state.current_project_dir / "issues").glob("*.json"))
    assert not issues


@then('the issue file in virtual project "{label}" should have status "{status}"')
def then_issue_status_virtual(context: object, label: str, status: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    issue_path = next((project.shared_dir / "issues").glob("*.json"))
    issue = read_issue_file(project.shared_dir, issue_path.stem)
    assert issue.status == status


@then('issue "{identifier}" in virtual project "{label}" should have 1 comment')
def then_issue_comment_virtual(context: object, identifier: str, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    issue = read_issue_file(project.shared_dir, identifier)
    assert len(issue.comments) == 1


@then('the issue file should not exist in virtual project "{label}"')
def then_issue_not_exist_virtual(context: object, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    assert not list((project.shared_dir / "issues").glob("*.json"))


@then('stdout should contain the source project label "{label}"')
def then_stdout_contains_source_label(context: object, label: str) -> None:
    assert label in context.result.stdout


@then('issue "{identifier}" should exist in virtual project "{label}" shared directory')
def then_issue_exists_shared_virtual(
    context: object, identifier: str, label: str
) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    assert (project.shared_dir / "issues" / f"{identifier}.json").exists()


@then(
    'issue "{identifier}" should not exist in virtual project "{label}" local directory'
)
def then_issue_missing_local_virtual(
    context: object, identifier: str, label: str
) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    assert not (project.local_dir / "issues" / f"{identifier}.json").exists()


@then('issue "{identifier}" should exist in virtual project "{label}" local directory')
def then_issue_exists_local_virtual(
    context: object, identifier: str, label: str
) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    assert (project.local_dir / "issues" / f"{identifier}.json").exists()


@then(
    'issue "{identifier}" should not exist in virtual project "{label}" shared directory'
)
def then_issue_missing_shared_virtual(
    context: object, identifier: str, label: str
) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    assert not (project.shared_dir / "issues" / f"{identifier}.json").exists()


@then('an event file should be created in virtual project "{label}" events directory')
def then_event_file_created(context: object, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    events = list(project.events_dir.glob("*.json"))
    assert events


@given("issues exist in multiple virtual projects")
def given_issues_multiple_virtual(context: object) -> None:
    state = _configure_virtual_projects(context, ["alpha", "beta"])
    _create_issue(state.current_project_dir, "kbs-001", "Current issue")
    _create_issue(
        state.virtual_projects["alpha"].shared_dir, "alpha-001", "Alpha issue"
    )
    _create_issue(state.virtual_projects["beta"].shared_dir, "beta-001", "Beta issue")


@given("issues exist in multiple virtual projects with various statuses")
def given_issues_multiple_statuses(context: object) -> None:
    state = _configure_virtual_projects(context, ["alpha", "beta"])
    _create_issue(
        state.virtual_projects["alpha"].shared_dir,
        "alpha-open",
        "Alpha open",
        status="open",
    )
    _create_issue(
        state.virtual_projects["alpha"].shared_dir,
        "alpha-closed",
        "Alpha closed",
        status="closed",
    )


@given('a virtual project "{label}" has local issues')
def given_virtual_project_alpha_local(context: object, label: str) -> None:
    state = _configure_virtual_projects(context, [label])
    _create_issue(
        state.virtual_projects[label].local_dir, f"{label}-local", "Local alpha"
    )


@given('a virtual project "{label}" has shared and local issues')
def given_virtual_project_alpha_shared_local(context: object, label: str) -> None:
    state = _configure_virtual_projects(context, [label])
    _create_issue(
        state.virtual_projects[label].shared_dir, f"{label}-shared", "Shared alpha"
    )
    _create_issue(
        state.virtual_projects[label].local_dir, f"{label}-local", "Local alpha"
    )


@then('stdout should contain issues from "{label}"')
def then_stdout_contains_issues_from(context: object, label: str) -> None:
    assert label in context.result.stdout


@then("stdout should not contain issues from other projects")
def then_stdout_not_contains_other_projects(context: object) -> None:
    assert "beta" not in context.result.stdout and "kbs" not in context.result.stdout


@then("stdout should contain issues from the current project only")
def then_stdout_current_only(context: object) -> None:
    stdout = context.result.stdout
    assert "kbs" in stdout and "alpha" not in stdout and "beta" not in stdout


@then("stdout should not contain issues from the current project")
def then_stdout_not_current(context: object) -> None:
    assert "kbs" not in context.result.stdout


@then('stdout should contain only local issues from "alpha"')
def then_stdout_only_local_alpha(context: object) -> None:
    stdout = context.result.stdout
    assert "alpha" in stdout and "local" in stdout and "shared" not in stdout


@then('stdout should contain only shared issues from "alpha"')
def then_stdout_only_shared_alpha(context: object) -> None:
    stdout = context.result.stdout
    assert "alpha" in stdout and "shared" in stdout and "local" not in stdout


@then('stdout should contain only open issues from "alpha"')
def then_stdout_only_open_alpha(context: object) -> None:
    stdout = context.result.stdout
    assert "alpha" in stdout and "closed" not in stdout


@then("stdout should contain issues from all projects")
def then_stdout_all_projects(context: object) -> None:
    stdout = context.result.stdout
    assert "kbs" in stdout and "alpha" in stdout and "beta" in stdout


@then("issues from all virtual projects should be listed")
def then_issues_from_all_virtual_projects(context: object) -> None:
    stdout = context.result.stdout
    for label in _ensure_virtual_state(context).virtual_projects.keys():
        assert label in stdout


@then("issues from the current project should be listed")
def then_issues_from_current_project(context: object) -> None:
    assert _ensure_virtual_state(context).current_label in context.result.stdout


@then("each issue should display its source project label")
def then_each_issue_has_label(context: object) -> None:
    stdout = context.result.stdout
    assert "alpha" in stdout or "beta" in stdout


@given("a virtual project has local issues")
def given_virtual_project_has_local(context: object) -> None:
    state = _configure_virtual_projects(context, ["alpha"])
    _create_issue(
        state.virtual_projects["alpha"].local_dir, "alpha-local", "Local issue"
    )


@then("local issues from the virtual project should be listed")
def then_local_issues_listed(context: object) -> None:
    assert "local" in context.result.stdout


@given("a Kanbus project with a virtual project pointing to a missing path")
def given_virtual_project_missing_path(context: object) -> None:
    state = _ensure_virtual_state(context)
    _set_primary_configuration_value(
        state.root,
        "virtual_projects",
        {"missing": {"path": "virtual/missing/project"}},
    )


@given("a Kanbus project with a virtual project pointing to a directory without issues")
def given_virtual_project_missing_issues(context: object) -> None:
    state = _ensure_virtual_state(context)
    (state.root / "virtual" / "hollow" / "project").mkdir(parents=True, exist_ok=True)
    _set_primary_configuration_value(
        state.root,
        "virtual_projects",
        {"hollow": {"path": "virtual/hollow/project"}},
    )


@given("a Kanbus project with duplicate virtual project labels")
def given_duplicate_virtual_labels(context: object) -> None:
    state = _ensure_virtual_state(context)
    config_path = state.root / ".kanbus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    payload.pop("virtual_projects", None)
    contents = yaml.safe_dump(payload, sort_keys=False)
    contents += (
        "virtual_projects:\n"
        "  alpha:\n    path: virtual/alpha/project\n"
        "  alpha:\n    path: virtual/beta/project\n"
    )
    config_path.write_text(contents, encoding="utf-8")


@given("a Kanbus project with a virtual project label matching the project key")
def given_virtual_label_conflict(context: object) -> None:
    _configure_virtual_projects(context, ["kbs"])


@given("a Kanbus repository with a .kanbus.yml file using external_projects")
def given_external_projects_config(context: object) -> None:
    state = _ensure_virtual_state(context)
    config_path = state.root / ".kanbus.yml"
    contents = config_path.read_text(encoding="utf-8")
    contents += "external_projects:\n  - ../elsewhere\n"
    config_path.write_text(contents, encoding="utf-8")


@given("a repository with a .kanbus.yml file with virtual projects configured")
def given_repo_with_virtual_projects_config(context: object) -> None:
    state = _configure_virtual_projects(context, ["extern"])
    _create_issue(
        state.virtual_projects["extern"].shared_dir, "kanbus-extern", "Extern"
    )


@then('stdout should contain the virtual project label for "{identifier}"')
def then_stdout_contains_virtual_label(context: object, identifier: str) -> None:
    label = _issue_project_label(_ensure_virtual_state(context), identifier)
    assert label is not None
    assert label in context.result.stdout


@then("issues from the virtual projects should be listed")
def then_issues_from_virtual_projects_listed(context: object) -> None:
    stdout = context.result.stdout
    assert "extern" in stdout or "alpha" in stdout
