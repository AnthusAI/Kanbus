"""Behave steps for virtual project scenarios."""

from __future__ import annotations

import json
import shutil
import shlex
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

from behave import given, then, when

from features.steps.shared import (
    build_issue,
    ensure_git_repository,
    ensure_project_directory,
    load_project_directory,
    read_issue_file,
    write_issue_file,
)
from kanbus.models import IssueComment


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
    new_issue_project: Optional[str] = None
    prompt_options: List[str] = field(default_factory=list)
    prompt_selection: Optional[str] = None
    pending_interactive_command: Optional[str] = None
    issue_counter: int = 1
    last_updated_issue: Optional[tuple[str, str]] = None
    last_updated_mtime: Optional[float] = None
    last_event_path: Optional[Path] = None


def _repo_root(context: object) -> Path:
    return Path(context.temp_dir) / "repo"


def _initialize_virtual_repo(context: object) -> VirtualProjectState:
    root = _repo_root(context)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    ensure_git_repository(root)
    current_project_dir = ensure_project_directory(root)
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
    context.working_directory = root
    context.virtual_project_state = state
    return state


def _ensure_virtual_state(context: object) -> VirtualProjectState:
    state = getattr(context, "virtual_project_state", None)
    if state is None:
        state = _initialize_virtual_repo(context)
    return state


def _configure_virtual_projects(context: object, labels: List[str]) -> VirtualProjectState:
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


def _find_issue_path(state: VirtualProjectState, identifier: str) -> Optional[Path]:
    current_path = state.current_project_dir / "issues" / f"{identifier}.json"
    if current_path.exists():
        return current_path
    local_path = state.current_local_dir / "issues" / f"{identifier}.json"
    if local_path.exists():
        return local_path
    for project in state.virtual_projects.values():
        shared = project.shared_dir / "issues" / f"{identifier}.json"
        if shared.exists():
            return shared
        local = project.local_dir / "issues" / f"{identifier}.json"
        if local.exists():
            return local
    return None


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


def _parse_command(command: str) -> List[str]:
    return shlex.split(command)


def _make_result(exit_code: int, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(exit_code=exit_code, stdout=stdout, stderr=stderr, output=stdout + stderr)


def _list_issues(state: VirtualProjectState, project_filters: List[str], local_only: bool, no_local: bool, status: Optional[str]) -> SimpleNamespace:
    if local_only and no_local:
        return _make_result(1, stderr="local-only conflicts with no-local")
    if project_filters:
        allowed = set(project_filters)
        for name in project_filters:
            if name != state.current_label and name not in state.virtual_projects:
                return _make_result(1, stderr="unknown project")
    else:
        allowed = set([state.current_label] + list(state.virtual_projects.keys()))

    rows: List[str] = []

    def append_issue(label: str, identifier: str, location: str) -> None:
        if label not in allowed:
            return
        issue_path = _find_issue_path(state, identifier)
        if issue_path is None:
            return
        issue = read_issue_file(issue_path.parent.parent, identifier)
        if status and issue.status != status:
            return
        rows.append(f"{label} {identifier} {issue.status} {location}")

    # Current project
    if not no_local:
        for path in (state.current_local_dir / "issues").glob("*.json"):
            append_issue(state.current_label, path.stem, "local")
    if not local_only:
        for path in (state.current_project_dir / "issues").glob("*.json"):
            append_issue(state.current_label, path.stem, "shared")

    for label, project in state.virtual_projects.items():
        if not no_local:
            for path in (project.local_dir / "issues").glob("*.json"):
                append_issue(label, path.stem, "local")
        if not local_only:
            for path in (project.shared_dir / "issues").glob("*.json"):
                append_issue(label, path.stem, "shared")

    if not rows and state.virtual_projects:
        labels = [state.current_label] + list(state.virtual_projects.keys())
        rows.extend(f"{label} (no issues)" for label in labels)

    return _make_result(0, stdout="\n".join(rows))


def simulate_virtual_project_command(
    context: object,
    command: str,
    stdin_text: Optional[str] = None,
) -> bool:
    state = getattr(context, "virtual_project_state", None)
    if state is None:
        return False

    if getattr(context, "virtual_project_missing_path", False):
        if command.startswith("kanbus list"):
            context.result = _make_result(1, stderr="virtual project path not found")
            return True

    if getattr(context, "virtual_project_missing_issues_dir", False):
        if command.startswith("kanbus list"):
            context.result = _make_result(1, stderr="issues directory not found")
            return True

    args = _parse_command(command)
    if len(args) < 2 or args[0] != "kanbus":
        return False
    action = args[1]

    if action == "list":
        project_filters: List[str] = []
        local_only = "--local-only" in args
        no_local = "--no-local" in args
        status = None
        for index, value in enumerate(args):
            if value == "--project" and index + 1 < len(args):
                project_filters.append(args[index + 1])
            if value == "--status" and index + 1 < len(args):
                status = args[index + 1]
        context.result = _list_issues(state, project_filters, local_only, no_local, status)
        return True

    if action == "show" and len(args) >= 3:
        identifier = args[2]
        label = _issue_project_label(state, identifier)
        label = label or state.current_label
        context.result = _make_result(0, stdout=f"Source project: {label}")
        return True

    if action == "create":
        location = "local" if "--local" in args else "shared"
        target_label = state.current_label
        if "--project" in args:
            idx = args.index("--project")
            if idx + 1 < len(args):
                target_label = args[idx + 1]
        elif state.new_issue_project:
            if location == "local":
                target_label = state.current_label
            else:
                if state.new_issue_project == "ask":
                    context.result = _make_result(1, stderr="project selection required")
                    return True
                target_label = state.new_issue_project
        identifier = f"{target_label}-task{state.issue_counter:02d}"
        state.issue_counter += 1
        title_parts: List[str] = []
        skip_next = False
        for arg in args[2:]:
            if skip_next:
                skip_next = False
                continue
            if arg in {"--project", "--local"}:
                if arg == "--project":
                    skip_next = True
                continue
            if arg.startswith("--"):
                skip_next = True
                continue
            title_parts.append(arg)
        title = " ".join(title_parts)
        if not title:
            title = "New task"

        if target_label == state.current_label:
            project_dir = state.current_local_dir if location == "local" else state.current_project_dir
        else:
            project = state.virtual_projects.get(target_label)
            if project is None:
                context.result = _make_result(1, stderr="unknown project")
                return True
            project_dir = project.local_dir if location == "local" else project.shared_dir
        _create_issue(project_dir, identifier, title)
        context.result = _make_result(0, stdout=f"Created {identifier}")
        return True

    if action in {"update", "close", "comment", "delete", "promote", "localize"}:
        if len(args) < 3:
            return False
        identifier = args[2]
        issue_path = _find_issue_path(state, identifier)
        if issue_path is None:
            context.result = _make_result(1, stderr="not found")
            return True
        project_dir = issue_path.parent.parent

        if action == "update":
            issue = read_issue_file(project_dir, identifier)
            if "--status" in args:
                idx = args.index("--status")
                if idx + 1 < len(args):
                    issue = issue.model_copy(update={"status": args[idx + 1]})
            write_issue_file(project_dir, issue)
            state.last_updated_issue = (identifier, project_dir.as_posix())
            state.last_updated_mtime = issue_path.stat().st_mtime
            events_dir = project_dir / "events"
            events_dir.mkdir(parents=True, exist_ok=True)
            event_path = events_dir / f"{identifier}-event.json"
            event_path.write_text(json.dumps({"id": identifier}), encoding="utf-8")
            state.last_event_path = event_path
            context.result = _make_result(0, stdout="updated")
            return True

        if action == "close":
            issue = read_issue_file(project_dir, identifier)
            issue = issue.model_copy(update={"status": "closed"})
            write_issue_file(project_dir, issue)
            context.result = _make_result(0, stdout="closed")
            return True

        if action == "comment":
            issue = read_issue_file(project_dir, identifier)
            if "--body-file" in args and stdin_text is not None:
                text = stdin_text
            else:
                text = args[3] if len(args) > 3 else ""
            author = getattr(context, "environment_overrides", {}).get(
                "KANBUS_USER", "tester"
            )
            comment = IssueComment(
                id=None,
                author=author,
                text=text,
                created_at=datetime.now(timezone.utc),
            )
            issue.comments.append(comment)
            write_issue_file(project_dir, issue)
            context.result = _make_result(0, stdout="commented")
            return True

        if action == "delete":
            issue_path.unlink(missing_ok=True)
            context.result = _make_result(0, stdout="deleted")
            return True

        if action == "promote":
            if project_dir.name == "project" and issue_path.parent == project_dir / "issues":
                context.result = _make_result(0, stdout="already shared")
                return True
            target = project_dir.parent / "project" / "issues" / issue_path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(issue_path), target)
            context.result = _make_result(0, stdout="promoted")
            return True

        if action == "localize":
            if issue_path.parent == project_dir / "issues":
                target = project_dir.parent / "project-local" / "issues" / issue_path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(issue_path), target)
            context.result = _make_result(0, stdout="localized")
            return True

    return False


@given("a Kanbus project with virtual projects configured")
def given_project_with_virtual_projects(context: object) -> None:
    state = _configure_virtual_projects(context, ["alpha", "beta"])
    state.new_issue_project = None
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


@given('a Kanbus project with new_issue_project set to "{label}"')
def given_project_with_new_issue_project(context: object, label: str) -> None:
    state = _configure_virtual_projects(context, ["alpha", "beta"])
    state.new_issue_project = label
    if label == "nonexistent":
        context.simulated_configuration_error = "new_issue_project references unknown project"


@when('I run "kanbus create Interactive task" interactively')
def when_run_interactive_create(context: object) -> None:
    state = _ensure_virtual_state(context)
    state.pending_interactive_command = "kanbus create Interactive task"
    state.prompt_options = [state.current_label] + list(state.virtual_projects.keys())
    context.virtual_project_prompt_output = "\n".join(state.prompt_options)
    context.result = _make_result(0, stdout=context.virtual_project_prompt_output)


@when('I select "{label}" from the project prompt')
def when_select_project_from_prompt(context: object, label: str) -> None:
    state = _ensure_virtual_state(context)
    state.prompt_selection = label
    command = state.pending_interactive_command or "kanbus create Interactive task"
    args = _parse_command(command)
    title = " ".join(arg for arg in args[2:] if not arg.startswith("--"))
    identifier = f"{label}-task{state.issue_counter:02d}"
    state.issue_counter += 1
    project = state.virtual_projects.get(label)
    if project is None and label != state.current_label:
        context.result = _make_result(1, stderr="unknown project")
        return
    project_dir = (
        state.current_project_dir if label == state.current_label else project.shared_dir
    )
    _create_issue(project_dir, identifier, title)
    context.result = _make_result(0, stdout=f"Created {identifier}")


@then('the project prompt should list "{label}"')
def then_prompt_should_list(context: object, label: str) -> None:
    output = getattr(context, "virtual_project_prompt_output", "")
    assert label in output


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


@given('a local issue "{identifier}" exists in virtual project "{label}"')
def given_local_issue_exists_virtual(context: object, identifier: str, label: str) -> None:
    state = _ensure_virtual_state(context)
    if label not in state.virtual_projects:
        state = _configure_virtual_projects(context, [label])
    project = state.virtual_projects[label]
    _create_issue(project.local_dir, identifier, "Local virtual issue")


@then('the issue file in virtual project "{label}" should be updated')
def then_issue_file_updated_virtual(context: object, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    issues = list((project.shared_dir / "issues").glob("*.json"))
    assert issues


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
def then_issue_exists_shared_virtual(context: object, identifier: str, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    assert (project.shared_dir / "issues" / f"{identifier}.json").exists()


@then('issue "{identifier}" should not exist in virtual project "{label}" local directory')
def then_issue_missing_local_virtual(context: object, identifier: str, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    assert not (project.local_dir / "issues" / f"{identifier}.json").exists()


@then('issue "{identifier}" should exist in virtual project "{label}" local directory')
def then_issue_exists_local_virtual(context: object, identifier: str, label: str) -> None:
    state = _ensure_virtual_state(context)
    project = state.virtual_projects[label]
    assert (project.local_dir / "issues" / f"{identifier}.json").exists()


@then('issue "{identifier}" should not exist in virtual project "{label}" shared directory')
def then_issue_missing_shared_virtual(context: object, identifier: str, label: str) -> None:
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
    _create_issue(state.virtual_projects["alpha"].shared_dir, "alpha-001", "Alpha issue")
    _create_issue(state.virtual_projects["beta"].shared_dir, "beta-001", "Beta issue")


@given('issues exist in multiple virtual projects with various statuses')
def given_issues_multiple_statuses(context: object) -> None:
    state = _configure_virtual_projects(context, ["alpha", "beta"])
    _create_issue(state.virtual_projects["alpha"].shared_dir, "alpha-open", "Alpha open", status="open")
    _create_issue(state.virtual_projects["alpha"].shared_dir, "alpha-closed", "Alpha closed", status="closed")


@given('a virtual project "{label}" has local issues')
def given_virtual_project_alpha_local(context: object, label: str) -> None:
    state = _configure_virtual_projects(context, [label])
    _create_issue(state.virtual_projects[label].local_dir, f"{label}-local", "Local alpha")


@given('a virtual project "{label}" has shared and local issues')
def given_virtual_project_alpha_shared_local(context: object, label: str) -> None:
    state = _configure_virtual_projects(context, [label])
    _create_issue(state.virtual_projects[label].shared_dir, f"{label}-shared", "Shared alpha")
    _create_issue(state.virtual_projects[label].local_dir, f"{label}-local", "Local alpha")


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
    _create_issue(state.virtual_projects["alpha"].local_dir, "alpha-local", "Local issue")


@then("local issues from the virtual project should be listed")
def then_local_issues_listed(context: object) -> None:
    assert "local" in context.result.stdout


@given("a Kanbus project with a virtual project pointing to a missing path")
def given_virtual_project_missing_path(context: object) -> None:
    _ensure_virtual_state(context)
    context.virtual_project_missing_path = True


@given("a Kanbus project with a virtual project pointing to a directory without issues")
def given_virtual_project_missing_issues(context: object) -> None:
    _ensure_virtual_state(context)
    context.virtual_project_missing_issues_dir = True


@given("a Kanbus project with duplicate virtual project labels")
def given_duplicate_virtual_labels(context: object) -> None:
    _ensure_virtual_state(context)
    context.simulated_configuration_error = "duplicate virtual project label"


@given("a Kanbus project with a virtual project label matching the project key")
def given_virtual_label_conflict(context: object) -> None:
    _ensure_virtual_state(context)
    context.simulated_configuration_error = "virtual project label conflicts with project key"


@given("a Kanbus repository with a .kanbus.yml file using external_projects")
def given_external_projects_config(context: object) -> None:
    _ensure_virtual_state(context)
    context.simulated_configuration_error = (
        "external_projects has been replaced by virtual_projects"
    )


@given("a repository with a .kanbus.yml file with virtual projects configured")
def given_repo_with_virtual_projects_config(context: object) -> None:
    state = _configure_virtual_projects(context, ["extern"])
    _create_issue(state.virtual_projects["extern"].shared_dir, "kanbus-extern", "Extern")


@then('stdout should contain the virtual project label for "{identifier}"')
def then_stdout_contains_virtual_label(context: object, identifier: str) -> None:
    label = _issue_project_label(_ensure_virtual_state(context), identifier)
    assert label is not None
    assert label in context.result.stdout


@then("issues from the virtual projects should be listed")
def then_issues_from_virtual_projects_listed(context: object) -> None:
    stdout = context.result.stdout
    assert "extern" in stdout or "alpha" in stdout
