"""Git-backed shared router state isolated from a user's checkout."""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path

from kanbus.config_loader import load_project_configuration
from kanbus.event_history import EventRecord, event_filename, write_events_batch
from kanbus.issue_router import IssueRouterError
from kanbus.project import get_configuration_path

STATE_BRANCH = "kanbus/router-state"
STATE_REF = f"refs/heads/{STATE_BRANCH}"
REMOTE_REF = f"refs/remotes/origin/{STATE_BRANCH}"


def router_state_root(source_root: Path, *, refresh: bool = True) -> Path:
    """Return the hidden router worktree, refreshing shared board state first.

    The worktree has its own checkout and index, so user dirt is never staged by
    the router. Only committed source changes and router-owned state are merged.
    """
    source_root = _repo_root(source_root)
    common_dir_text = _git(source_root, "rev-parse", "--git-common-dir").strip()
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = (source_root / common_dir).resolve()
    target = common_dir / "kanbus-router-state-worktree"

    _fetch_state(source_root)
    branch_exists = _ref_sha(source_root, STATE_REF) is not None
    remote_exists = _try_git(source_root, "show-ref", "--verify", REMOTE_REF)

    if not target.exists():
        if branch_exists:
            _git(source_root, "worktree", "add", str(target), STATE_BRANCH)
        else:
            base_ref = REMOTE_REF if remote_exists else "HEAD"
            _git(
                source_root,
                "worktree",
                "add",
                "-b",
                STATE_BRANCH,
                str(target),
                base_ref,
            )
    else:
        registered = _try_git(source_root, "worktree", "list", "--porcelain")
        if str(target) not in registered:
            raise IssueRouterError("router state worktree path is occupied")
        current_branch = _git(target, "branch", "--show-current").strip()
        if current_branch != STATE_BRANCH:
            raise IssueRouterError("router state worktree is on an unexpected branch")

    if refresh:
        # Merge remote router state, then the caller's committed board head. A
        # conflict is deliberately fatal: the scheduler must not plan on an
        # ambiguous board or overwrite another router's claim.
        if remote_exists:
            _merge_ref(target, REMOTE_REF)
        source_head = _git(source_root, "rev-parse", "HEAD").strip()
        if source_head != _git(target, "rev-parse", "HEAD").strip():
            _merge_ref(target, source_head)
    return target


def publish_router_state(source_root: Path, issue_ids: set[str] | None = None) -> str:
    """Commit and lease-push router mutations without touching the user index.

    Event files are immutable and issue files are selected explicitly. The
    hidden worktree is rebased on the latest router branch before every push;
    bounded retries make concurrent unrelated router events converge.
    """
    worktree = router_state_root(source_root, refresh=True)
    config_path = get_configuration_path(worktree)
    configuration = load_project_configuration(config_path)
    project_path = Path(configuration.project_directory)
    event_path = project_path / "events"
    # Kanbus keeps the local event stream ignored in user checkouts, but the
    # router's isolated state branch is its deliberate cross-clone publisher.
    add_args = ["add", "-f", "--", event_path.as_posix()]
    if issue_ids:
        add_args.extend(
            (project_path / "issues" / f"{issue_id}.json").as_posix()
            for issue_id in sorted(issue_ids)
        )
    _git(worktree, *add_args)
    staged = _git(worktree, "diff", "--cached", "--name-only", "-z")
    if not staged:
        return _git(worktree, "rev-parse", "HEAD").strip()

    changed_paths = {path for path in staged.split("\0") if path}
    if any(
        path != event_path.as_posix()
        and not path.startswith(f"{event_path.as_posix()}/")
        and not path.startswith(f"{project_path.as_posix()}/issues/")
        for path in changed_paths
    ):
        raise IssueRouterError("router state publication selected an unsafe path")
    _git(
        worktree,
        "-c",
        "user.name=Kanbus Issue Router",
        "-c",
        "user.email=issue-router@localhost",
        "commit",
        "-m",
        "kanbus: publish router state",
    )

    if _try_git(worktree, "remote", "get-url", "origin") is None:
        return _git(worktree, "rev-parse", "HEAD").strip()
    for _attempt in range(5):
        _fetch_state(worktree)
        remote_sha = _ref_sha(worktree, REMOTE_REF)
        local_sha = _git(worktree, "rev-parse", "HEAD").strip()
        if remote_sha is not None and not _is_ancestor(worktree, remote_sha, local_sha):
            _merge_ref(worktree, REMOTE_REF)
            local_sha = _git(worktree, "rev-parse", "HEAD").strip()
        lease = f"--force-with-lease={STATE_REF}:{remote_sha or ''}"
        result = _try_git(
            worktree,
            "push",
            lease,
            "origin",
            f"HEAD:{STATE_REF}",
            capture=True,
        )
        if isinstance(result, int) and result == 0:
            return local_sha
        # A failed lease means another writer won. Refresh and replay only the
        # already validated immutable/additive state commit.
        _fetch_state(worktree)
        latest_sha = _ref_sha(worktree, REMOTE_REF)
        if latest_sha and not _is_ancestor(worktree, latest_sha, local_sha):
            _merge_ref(worktree, REMOTE_REF)
            local_sha = _git(worktree, "rev-parse", "HEAD").strip()
    raise IssueRouterError("could not publish router state after 5 retries")


def publish_router_start_event(
    source_root: Path,
    event: EventRecord,
    *,
    validate_claim: Callable[[Path], None],
) -> str:
    """Publish a start event only after validating its claim on the shared tip.

    The event is written into a disposable router-state worktree. A losing or
    stale claimant therefore cannot leave a local started event that a later
    release/renewal publication would accidentally share.

    :param source_root: Repository or router-state worktree root.
    :type source_root: Path
    :param event: Canonical started event to publish.
    :type event: EventRecord
    :param validate_claim: Callback that raises if the claim is no longer current.
    :type validate_claim: Callable[[Path], None]
    :return: Commit that published the start event.
    :rtype: str
    :raises IssueRouterError: If validation or shared publication fails.
    """
    source_root = _repo_root(source_root)
    source_state = router_state_root(source_root, refresh=True)
    if _try_git(source_state, "remote", "get-url", "origin") is None:
        configuration = load_project_configuration(get_configuration_path(source_state))
        events_dir = source_state / configuration.project_directory / "events"
        validate_claim(events_dir)
        write_events_batch(events_dir, [event])
        return publish_router_state(source_state)

    for _attempt in range(5):
        _fetch_state(source_state)
        remote_sha = _ref_sha(source_state, REMOTE_REF)
        base = remote_sha or _git(source_state, "rev-parse", "HEAD").strip()
        worktree = (
            Path(tempfile.gettempdir())
            / f".kanbus-router-start-{os.getpid()}-{uuid.uuid4().hex}"
        )
        _git(source_state, "worktree", "add", "--detach", str(worktree), base)
        try:
            source_head = _git(source_state, "rev-parse", "HEAD").strip()
            temp_head = _git(worktree, "rev-parse", "HEAD").strip()
            if source_head != temp_head and not _is_ancestor(
                worktree, source_head, temp_head
            ):
                _merge_ref(worktree, source_head)
            configuration = load_project_configuration(get_configuration_path(worktree))
            project_path = Path(configuration.project_directory)
            events_dir = worktree / project_path / "events"
            validate_claim(events_dir)
            write_events_batch(events_dir, [event])
            relative_event = (
                project_path
                / "events"
                / event_filename(event.occurred_at, event.event_id)
            ).as_posix()
            _git(worktree, "add", "-f", "--", relative_event)
            _git(
                worktree,
                "-c",
                "user.name=Kanbus Issue Router",
                "-c",
                "user.email=issue-router@localhost",
                "commit",
                "-m",
                f"kanbus: publish router start {event.event_id}",
            )
            lease = f"--force-with-lease={STATE_REF}:{remote_sha or ''}"
            result = _try_git(
                worktree,
                "push",
                lease,
                "origin",
                f"HEAD:{STATE_REF}",
                capture=True,
            )
            if result == 0:
                router_state_root(source_state, refresh=True)
                return _git(worktree, "rev-parse", "HEAD").strip()
            _fetch_state(source_state)
            latest_sha = _ref_sha(source_state, REMOTE_REF)
            if latest_sha == remote_sha:
                raise IssueRouterError("could not publish router start event")
        finally:
            _try_git(
                source_state,
                "worktree",
                "remove",
                "--force",
                str(worktree),
                capture=True,
            )
    raise IssueRouterError("could not publish router start event after 5 retries")


def _fetch_state(root: Path) -> None:
    if _try_git(root, "remote", "get-url", "origin") is None:
        return
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        advertised = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", STATE_REF],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        raise IssueRouterError("could not fetch shared router state")
    if not advertised.strip():
        return
    result = _try_git(
        root,
        "fetch",
        "--no-tags",
        "origin",
        f"+{STATE_REF}:{REMOTE_REF}",
        capture=True,
    )
    if result != 0:
        raise IssueRouterError("could not fetch shared router state")


def _merge_ref(root: Path, ref: str) -> None:
    # Router worktrees have no dependency on the user's Git identity. A merge
    # commit is needed when independent routers advance the state ref from a
    # common base, so give only this internal merge a stable local identity.
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Kanbus Issue Router",
            "-c",
            "user.email=issue-router@localhost",
            "merge",
            # The incoming revision is authoritative: it is either the
            # latest shared router-state tip or the caller's committed board
            # head.  Router records are append-only, so preferring it for an
            # overlapping issue snapshot avoids stranding a scheduler merely
            # because a human status change and a router event touched the
            # same JSON file.
            "-X",
            "theirs",
            "--no-edit",
            ref,
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _try_git(root, "merge", "--abort", capture=True)
        detail = result.stderr.strip() or result.stdout.strip() or "merge failed"
        raise IssueRouterError(
            "router state reconciliation conflicted; no package was started: " + detail
        )


def _repo_root(root: Path) -> Path:
    return Path(_git(root, "rev-parse", "--show-toplevel").strip()).resolve()


def resolve_router_root(root: Path) -> Path:
    """Resolve the enclosing Git repository root for router operations.

    Router commands must establish this boundary before loading configuration
    or shared state. Keeping the diagnostic stable also prevents raw Git
    errors from leaking into the command-line contract.
    """
    try:
        return _repo_root(root)
    except IssueRouterError as error:
        raise IssueRouterError("issue router requires a Git repository") from error


def _git(root: Path, *args: str) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr.strip()
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        raise IssueRouterError(detail or "router Git operation failed") from error
    return completed.stdout


def _try_git(root: Path, *args: str, capture: bool = False) -> str | int | None:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError:
        return None
    if capture:
        return completed.returncode
    return completed.stdout if completed.returncode == 0 else None


def _ref_sha(root: Path, ref: str) -> str | None:
    result = _try_git(root, "rev-parse", "--verify", ref)
    return str(result).strip() if result is not None else None


def _is_ancestor(root: Path, older: str, newer: str) -> bool:
    return (
        _try_git(root, "merge-base", "--is-ancestor", older, newer, capture=True) == 0
    )
