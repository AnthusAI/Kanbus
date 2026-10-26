"""Behave steps for router host hygiene and credential handling."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from behave import given, then, when

from kanbus.coordination_mutex_api import MutexApiUnavailable, acquire
from kanbus.models import MutexApiConfiguration
from kanbus.router_adapters import opencode_data_directory
from kanbus.router_conversation import redact_text
from kanbus.router_execution import (
    _adapter_process_record_path,
    finish_package_resources,
    prune_stale_worktrees,
    router_worktree_root,
)

PLACEHOLDER_BEARER_TOKEN = "placeholder-token"


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _registered_worktrees(root: Path) -> list[Path]:
    listing = _git(root, "worktree", "list", "--porcelain")
    return [
        Path(line.removeprefix("worktree "))
        for line in listing.splitlines()
        if line.startswith("worktree ")
    ]


def _worktree_path(context: object, package: str, claim: str) -> Path:
    return router_worktree_root(context.hygiene_root) / f"{package}-{claim}"


def _package_has_registered_worktree(context: object, package: str) -> bool:
    return any(
        path.name.startswith(f"{package}-")
        for path in _registered_worktrees(context.hygiene_root)
    )


@given("a router test repository")
def given_router_test_repository(context: object) -> None:
    directory = tempfile.mkdtemp(prefix="kanbus-hygiene-")
    context.add_cleanup(shutil.rmtree, directory, True)
    root = Path(directory).resolve()
    _git(root, "init", "--quiet")
    _git(root, "config", "user.email", "hygiene@example.test")
    _git(root, "config", "user.name", "Hygiene Test")
    (root / "README.md").write_text("hygiene\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "--quiet", "-m", "initial")
    context.hygiene_root = root


@then(
    'the router worktree for package "{package}" claim "{claim}" should be inside the git common directory'
)
def then_worktree_inside_common_directory(
    context: object, package: str, claim: str
) -> None:
    common = Path(_git(context.hygiene_root, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = context.hygiene_root / common
    path = _worktree_path(context, package, claim).resolve()
    assert common.resolve() in path.parents, f"{path} is outside {common}"


@given('a registered router worktree for package "{package}" claim "{claim}"')
def given_registered_router_worktree(context: object, package: str, claim: str) -> None:
    path = _worktree_path(context, package, claim)
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(
        context.hygiene_root,
        "worktree",
        "add",
        "--detach",
        str(path),
        "HEAD",
    )


@given('an OpenCode data directory holding a credentials copy for package "{package}"')
def given_opencode_data_directory(context: object, package: str) -> None:
    state_directory = _adapter_process_record_path(
        context.hygiene_root, package, ""
    ).parent
    credentials = opencode_data_directory(state_directory, package) / "opencode"
    credentials.mkdir(parents=True)
    (credentials / "auth.json").write_text("{}\n", encoding="utf-8")
    context.hygiene_state_directory = state_directory


@given('the directory of the router worktree for package "{package}" was deleted')
def given_worktree_directory_deleted(context: object, package: str) -> None:
    for path in _registered_worktrees(context.hygiene_root):
        if path.name.startswith(f"{package}-"):
            shutil.rmtree(path)


@when('the router finishes package "{package}" with a terminal outcome')
def when_router_finishes_package(context: object, package: str) -> None:
    finish_package_resources(context.hygiene_root, package)


@when("the router prunes stale worktrees")
def when_router_prunes_stale_worktrees(context: object) -> None:
    prune_stale_worktrees(context.hygiene_root)


@then('no router worktree should remain registered for package "{package}"')
def then_no_worktree_remains(context: object, package: str) -> None:
    assert not _package_has_registered_worktree(context, package)
    assert not any(
        path.name.startswith(f"{package}-")
        for path in router_worktree_root(context.hygiene_root).glob("*")
    )


@then('a router worktree should remain registered for package "{package}"')
def then_worktree_remains(context: object, package: str) -> None:
    assert _package_has_registered_worktree(context, package)


@then('no OpenCode data directory should remain for package "{package}"')
def then_no_opencode_data_remains(context: object, package: str) -> None:
    directory = opencode_data_directory(context.hygiene_state_directory, package)
    assert not directory.exists(), f"{directory} still exists"
    assert not list(directory.parent.rglob("auth.json"))


@given(
    'agent output with a {family} credential assembled from "{prefix}" and "{body}" joined by {joiner} between two text lines'
)
def given_agent_output_with_credential(
    context: object, family: str, prefix: str, body: str, joiner: str
) -> None:
    separator = " " if joiner == "space" else ""
    context.hygiene_output = f"first line\n{prefix}{separator}{body}\nlast line"


@when("the agent output is redacted for persistence")
def when_agent_output_is_redacted(context: object) -> None:
    context.hygiene_redacted = redact_text(context.hygiene_output)


@then("the redacted output should have {count:d} lines")
def then_redacted_output_line_count(context: object, count: int) -> None:
    assert len(context.hygiene_redacted.split("\n")) == count, context.hygiene_redacted


@then('the redacted output should not contain "{text}"')
def then_redacted_output_lacks(context: object, text: str) -> None:
    assert text not in context.hygiene_redacted, context.hygiene_redacted


@then('the redacted output should contain "{text}"')
def then_redacted_output_contains(context: object, text: str) -> None:
    assert text in context.hygiene_redacted, context.hygiene_redacted


@given('a mutex API client configuration with endpoint "{endpoint}" and a bearer token')
def given_mutex_client_configuration(context: object, endpoint: str) -> None:
    context.hygiene_mutex_configuration = MutexApiConfiguration.model_construct(
        endpoint=endpoint, bearer_token=PLACEHOLDER_BEARER_TOKEN
    )


@when("the mutex API client acquires a lease")
def when_mutex_client_acquires_lease(context: object) -> None:
    context.hygiene_mutex_error = None
    try:
        acquire(
            context.hygiene_mutex_configuration,
            resource="router:issue:kbs-hygiene",
            owner="hygiene",
            claim_id="claim-hygiene",
            revision=1,
            ttl_seconds=60,
        )
    except MutexApiUnavailable as error:
        context.hygiene_mutex_error = str(error)


@then('the mutex API client error should be "{message}"')
def then_mutex_client_error(context: object, message: str) -> None:
    assert context.hygiene_mutex_error == message, context.hygiene_mutex_error
