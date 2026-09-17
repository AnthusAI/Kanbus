"""Forge-neutral pull request operations and GitHub implementation."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any, Callable, Protocol
from urllib.parse import quote

import requests
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kanbus.issue_router import (
    IssueRouterError,
    _decode_router_event,
    load_router_context,
    record_router_event,
)
from kanbus.models import IssueRouterConfiguration
from kanbus.issue_update import IssueUpdateError, update_issue


class ForgePullRequest(BaseModel):
    """Pull request identity and current head."""

    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1)
    url: str
    head_branch: str
    head_sha: str
    state: str
    merged: bool = False


class GitHubPullRequestEvent(BaseModel):
    """Validated GitHub pull request event accepted by the router."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(strict=True, ge=1)
    event_id: str = Field(min_length=1)
    kind: str
    action: str
    repository: str
    number: int = Field(ge=1)
    head_sha: str = Field(min_length=1)
    merged: bool


class GitHubCheckRunEvent(BaseModel):
    """Validated completion event for a check run attached to a routed PR."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(strict=True, ge=1)
    event_id: str = Field(min_length=1)
    kind: str
    action: str
    repository: str
    number: int = Field(ge=1)
    head_sha: str = Field(min_length=1)
    conclusion: str


class PullRequestForge(Protocol):
    """Forge operations required for router publication and reconciliation."""

    def create_or_observe_pull_request(
        self,
        *,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
    ) -> ForgePullRequest:
        """Create a pull request or return the one already open for this head."""

    def observe_pull_request(self, number: int) -> dict[str, Any]:
        """Return the current forge payload for one pull request."""

    def list_check_runs(self, number: int, head_sha: str) -> list[dict[str, Any]]:
        """Return check runs associated with the current pull request head."""

    def list_pull_request_reviews(self, number: int) -> list[dict[str, Any]]:
        """Return all review submissions for one pull request.

        :param number: Pull request number.
        :type number: int
        :return: Review submissions in GitHub's API order.
        :rtype: list[dict[str, Any]]
        """


class GitHubForge:
    """GitHub REST API implementation of the forge boundary."""

    def __init__(
        self,
        *,
        repository: str,
        token: str,
        api_url: str = "https://api.github.com",
    ) -> None:
        self.repository = repository
        self.token = token
        self.api_url = api_url.rstrip("/")

    @classmethod
    def from_configuration(
        cls, configuration: IssueRouterConfiguration
    ) -> "GitHubForge":
        """Construct a GitHub client using the configured token environment name.

        :param configuration: Validated router configuration.
        :type configuration: IssueRouterConfiguration
        :return: Authenticated GitHub forge client.
        :rtype: GitHubForge
        :raises IssueRouterError: If GitHub is not configured or token is missing.
        """
        forge = configuration.forge
        if forge is None:
            raise IssueRouterError("router GitHub forge is not configured")
        token = os.environ.get(forge.token_env, "").strip()
        if not token:
            raise IssueRouterError(
                f"GitHub token environment variable {forge.token_env} is not set"
            )
        return cls(
            repository=forge.repository,
            token=token,
            api_url=forge.api_url,
        )

    def create_or_observe_pull_request(
        self,
        *,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
    ) -> ForgePullRequest:
        """Create an idempotent pull request for the requested branch.

        :param title: Pull request title.
        :type title: str
        :param body: Pull request description.
        :type body: str
        :param head_branch: Published router branch.
        :type head_branch: str
        :param base_branch: Configured target branch.
        :type base_branch: str
        :return: Pull request identity.
        :rtype: ForgePullRequest
        :raises IssueRouterError: If GitHub rejects or cannot serve the request.
        """
        existing = self._request(
            "GET",
            f"/repos/{self.repository}/pulls",
            params={
                "state": "all",
                "head": f"{self.repository.split('/')[0]}:{head_branch}",
            },
        )
        if isinstance(existing, list):
            for item in existing:
                if item.get("head", {}).get("ref") == head_branch:
                    return _pull_request_from_github(item)
        created = self._request(
            "POST",
            f"/repos/{self.repository}/pulls",
            payload={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
            },
        )
        if not isinstance(created, dict):
            raise IssueRouterError("GitHub returned an invalid pull request")
        return _pull_request_from_github(created)

    def observe_pull_request(self, number: int) -> dict[str, Any]:
        """Read one pull request from GitHub.

        :param number: Pull request number.
        :type number: int
        :return: GitHub pull request response.
        :rtype: dict[str, Any]
        :raises IssueRouterError: If GitHub rejects or cannot serve the request.
        """
        result = self._request("GET", f"/repos/{self.repository}/pulls/{number}")
        if not isinstance(result, dict):
            raise IssueRouterError("GitHub returned an invalid pull request")
        return result

    def list_check_runs(self, number: int, head_sha: str) -> list[dict[str, Any]]:
        """Read check runs for the current pull request commit."""
        del number  # The GitHub API queries check runs by commit SHA.
        check_runs: list[dict[str, Any]] = []
        page = 1
        while True:
            result = self._request(
                "GET",
                f"/repos/{self.repository}/commits/{quote(head_sha, safe='')}/check-runs",
                params={"per_page": "100", "page": str(page)},
            )
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("check_runs"), list)
                or any(not isinstance(item, dict) for item in result["check_runs"])
            ):
                raise IssueRouterError("GitHub returned invalid check runs")
            check_runs.extend(result["check_runs"])
            if len(result["check_runs"]) < 100:
                return check_runs
            page += 1

    def list_pull_request_reviews(self, number: int) -> list[dict[str, Any]]:
        """Read all review submissions for a pull request.

        :param number: Pull request number.
        :type number: int
        :return: Review submissions from every API page.
        :rtype: list[dict[str, Any]]
        :raises IssueRouterError: If GitHub returns an invalid review response.
        """
        reviews: list[dict[str, Any]] = []
        page = 1
        while True:
            result = self._request(
                "GET",
                f"/repos/{self.repository}/pulls/{number}/reviews",
                params={"per_page": "100", "page": str(page)},
            )
            if not isinstance(result, list) or any(
                not isinstance(item, dict) for item in result
            ):
                raise IssueRouterError("GitHub returned invalid pull request reviews")
            reviews.extend(result)
            if len(result) < 100:
                return reviews
            page += 1

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        payload: dict[str, str] | None = None,
    ) -> Any:
        url = f"{self.api_url}{path}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=payload,
                headers=headers,
                timeout=15,
            )
        except requests.RequestException as error:
            raise IssueRouterError("GitHub API unavailable") from error
        if response.status_code >= 400:
            raise IssueRouterError(f"GitHub API returned status {response.status_code}")
        try:
            return response.json() if response.content else None
        except ValueError as error:
            raise IssueRouterError("GitHub returned invalid JSON") from error


class FakeForge:
    """In-memory forge for deterministic router tests."""

    def __init__(self) -> None:
        self.pull_requests: dict[int, dict[str, Any]] = {}
        self.check_runs: dict[tuple[int, str], list[dict[str, Any]]] = {}
        self.pull_request_reviews: dict[int, list[dict[str, Any]]] = {}
        self.next_number = 1

    def create_or_observe_pull_request(
        self,
        *,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str,
    ) -> ForgePullRequest:
        """Create or reuse an in-memory pull request.

        :param title: Pull request title.
        :type title: str
        :param body: Pull request description.
        :type body: str
        :param head_branch: Published router branch.
        :type head_branch: str
        :param base_branch: Configured target branch.
        :type base_branch: str
        :return: Pull request identity.
        :rtype: ForgePullRequest
        """
        del base_branch
        for payload in self.pull_requests.values():
            if payload["head_branch"] == head_branch:
                return ForgePullRequest.model_validate(
                    {key: payload[key] for key in ForgePullRequest.model_fields}
                )
        number = self.next_number
        self.next_number += 1
        payload = {
            "number": number,
            "url": f"https://github.example/pull/{number}",
            "head_branch": head_branch,
            "head_sha": "fixture-head",
            "state": "open",
            "merged": False,
            "title": title,
            "body": body,
        }
        self.pull_requests[number] = payload
        return ForgePullRequest.model_validate(
            {key: payload[key] for key in ForgePullRequest.model_fields}
        )

    def observe_pull_request(self, number: int) -> dict[str, Any]:
        """Return an in-memory pull request.

        :param number: Pull request number.
        :type number: int
        :return: Pull request state.
        :rtype: dict[str, Any]
        :raises IssueRouterError: If the pull request does not exist.
        """
        if number not in self.pull_requests:
            raise IssueRouterError(f"unknown fake pull request {number}")
        return dict(self.pull_requests[number])

    def list_check_runs(self, number: int, head_sha: str) -> list[dict[str, Any]]:
        """Return configured check runs for deterministic tests."""
        return [dict(run) for run in self.check_runs.get((number, head_sha), [])]

    def list_pull_request_reviews(self, number: int) -> list[dict[str, Any]]:
        """Return configured reviews for deterministic tests.

        :param number: Pull request number.
        :type number: int
        :return: Review submissions for the pull request.
        :rtype: list[dict[str, Any]]
        """
        return [dict(review) for review in self.pull_request_reviews.get(number, [])]


def record_github_pull_request_event(
    project_dir,
    router_configuration: IssueRouterConfiguration,
    event_payload: dict[str, Any],
    *,
    package_issues: dict[str, list[str]] | None = None,
    before_mutation: Callable[[], None] | None = None,
) -> bool:
    """Record an idempotent, ownership-checked GitHub pull request event.

    :param project_dir: Kanbus project directory.
    :type project_dir: Path
    :param router_configuration: Validated router configuration.
    :type router_configuration: IssueRouterConfiguration
    :param event_payload: GitHub event envelope.
    :type event_payload: dict[str, Any]
    :param package_issues: Optional package identifier to issue identifier mapping.
    :type package_issues: dict[str, list[str]] | None
    :return: ``True`` when the event was newly recorded.
    :rtype: bool
    :raises IssueRouterError: If the event is malformed or not owned by the router.
    """
    try:
        event = GitHubPullRequestEvent.model_validate(event_payload)
    except ValidationError as error:
        raise IssueRouterError("invalid GitHub pull request event") from error
    forge = router_configuration.forge
    if event.kind != "pull_request" or event.action not in {
        "opened",
        "synchronize",
        "requested_changes",
        "approved",
        "closed",
    }:
        raise IssueRouterError("invalid GitHub pull request event")
    if forge is None:
        raise IssueRouterError("router GitHub forge is not configured")
    if event.repository != forge.repository:
        raise IssueRouterError(
            f'GitHub event repository "{event.repository}" does not match configured repository "{forge.repository}"'
        )
    all_events = _all_router_events(project_dir)
    duplicate = any(
        record.get("payload", {}).get("forge_event_id") == event.event_id
        for record in all_events
    )
    ownership = next(
        (
            record
            for record in reversed(all_events)
            if record.get("event_type") == "router_pull_request_opened"
            and record.get("payload", {}).get("number") == event.number
        ),
        None,
    )
    if ownership is None:
        raise IssueRouterError(
            f"GitHub pull request {event.number} is not owned by the Issue Router"
        )
    package_id = str(ownership["issue_id"]).removeprefix("router:")
    previous_head = str(ownership.get("payload", {}).get("head_sha", ""))
    if (
        event.action not in {"synchronize", "opened"}
        and previous_head != event.head_sha
    ):
        raise IssueRouterError(
            f"GitHub pull request {event.number} is not owned by the Issue Router"
        )
    if duplicate:
        _apply_forge_transition(
            project_dir,
            package_id,
            event.action,
            event,
            before_mutation=before_mutation,
        )
        return False
    if event.action in {"opened", "synchronize"}:
        _before_mutation(before_mutation)
        record_router_event(
            project_dir,
            package_id=package_id,
            event_type="router_pull_request_opened",
            payload={
                "number": event.number,
                "head_sha": event.head_sha,
                "repository": event.repository,
                "forge_event_id": event.event_id,
            },
        )
    elif event.action == "requested_changes":
        _before_mutation(before_mutation)
        record_router_event(
            project_dir,
            package_id=package_id,
            event_type="router_forge_event",
            payload={
                "action": "requested_changes",
                "number": event.number,
                "head_sha": event.head_sha,
                "forge_event_id": event.event_id,
            },
        )
    elif event.action == "approved":
        _before_mutation(before_mutation)
        record_router_event(
            project_dir,
            package_id=package_id,
            event_type="router_pull_request_approved",
            payload={
                "number": event.number,
                "head_sha": event.head_sha,
                "forge_event_id": event.event_id,
            },
        )
    else:
        _before_mutation(before_mutation)
        record_router_event(
            project_dir,
            package_id=package_id,
            event_type="router_pull_request_closed",
            payload={
                "number": event.number,
                "head_sha": event.head_sha,
                "merged": event.merged,
                "forge_event_id": event.event_id,
            },
        )
    if (
        event.action == "closed"
        and event.merged
        and not _approved_head(project_dir, package_id, event.head_sha)
    ):
        _before_mutation(before_mutation)
        record_router_event(
            project_dir,
            package_id=package_id,
            event_type="router_forge_event",
            payload={
                "action": "merged_unapproved",
                "number": event.number,
                "head_sha": event.head_sha,
                "diagnostic": "merged pull request has no approval for its current head",
            },
        )
    _apply_forge_transition(
        project_dir,
        package_id,
        event.action,
        event,
        before_mutation=before_mutation,
    )
    return True


def record_github_check_run_event(
    project_dir,
    router_configuration,
    payload,
    *,
    before_mutation: Callable[[], None] | None = None,
) -> bool:
    """Record a check-run event and requeue only a failed current PR head."""
    try:
        event = GitHubCheckRunEvent.model_validate(payload)
    except ValidationError as error:
        raise IssueRouterError("invalid GitHub check-run event") from error
    if event.kind != "check_run" or event.action != "completed":
        raise IssueRouterError("invalid GitHub check-run event")
    forge = router_configuration.forge
    if forge is None or event.repository != forge.repository:
        raise IssueRouterError("GitHub check-run repository does not match router")
    if event.conclusion not in {
        "success",
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
    }:
        raise IssueRouterError("invalid GitHub check-run conclusion")
    all_events = _all_router_events(project_dir)
    duplicate = any(
        item.get("payload", {}).get("forge_event_id") == event.event_id
        for item in all_events
    )
    ownership = next(
        (
            item
            for item in reversed(all_events)
            if item.get("event_type") == "router_pull_request_opened"
            and item.get("payload", {}).get("number") == event.number
        ),
        None,
    )
    if (
        ownership is None
        or ownership.get("payload", {}).get("head_sha") != event.head_sha
    ):
        raise IssueRouterError(
            f"GitHub pull request {event.number} is not owned by the Issue Router"
        )
    package_id = str(ownership["issue_id"]).removeprefix("router:")
    failure = event.conclusion != "success"
    if not duplicate:
        _before_mutation(before_mutation)
        record_router_event(
            project_dir,
            package_id=package_id,
            event_type="router_forge_event",
            payload={
                "action": "check_run_failure" if failure else "check_run_success",
                "number": event.number,
                "head_sha": event.head_sha,
                "conclusion": event.conclusion,
                "forge_event_id": event.event_id,
            },
        )
    _apply_forge_transition(
        project_dir,
        package_id,
        "requested_changes" if failure else "approved",
        SimpleNamespace(head_sha=event.head_sha, merged=False),
        before_mutation=before_mutation,
    )
    return not duplicate


def _approved_head(project_dir, package_id: str, head_sha: str) -> bool:
    return any(
        item.get("issue_id") == f"router:{package_id}"
        and item.get("event_type") == "router_pull_request_approved"
        and item.get("payload", {}).get("head_sha") == head_sha
        for item in _all_router_events(project_dir)
    )


def _apply_forge_transition(
    project_dir,
    package_id: str,
    action: str,
    event,
    *,
    before_mutation: Callable[[], None] | None = None,
) -> None:
    """Apply an owned forge lifecycle event through canonical issue mutation."""
    root = next(
        (
            candidate
            for candidate in project_dir.parents
            if (candidate / ".kanbus.yml").is_file()
        ),
        None,
    )
    if root is None:
        raise IssueRouterError("router project configuration could not be located")
    context = load_router_context(root)
    if action in {"opened", "synchronize", "approved"}:
        target_status = context.router.workflow.review
    elif action == "requested_changes":
        target_status = context.router.workflow.active
    elif not event.merged:
        target_status = context.router.workflow.blocked
    else:
        approved_head = _approved_head(project_dir, package_id, event.head_sha)
        target_status = (
            context.router.workflow.terminal[0]
            if approved_head
            else context.router.workflow.review
        )
    issue = next(
        (item for item in context.issues if item.identifier == package_id), None
    )
    if issue is None:
        raise IssueRouterError(f'unknown router package "{package_id}"')
    if issue.status != target_status:
        _before_mutation(before_mutation)
        try:
            update_issue(
                root,
                package_id,
                title=None,
                description=None,
                status=target_status,
                assignee=None,
                claim=False,
                regenerate_right_now=False,
            )
        except IssueUpdateError as error:
            raise IssueRouterError(str(error)) from error
    from kanbus.router_state import publish_router_state

    _before_mutation(before_mutation)
    publish_router_state(root, {package_id})


def _before_mutation(callback: Callable[[], None] | None) -> None:
    """Run a scheduler fence immediately before a durable mutation.

    :param callback: Optional fence supplied by the active scheduler.
    :type callback: Callable[[], None] | None
    """
    if callback is not None:
        callback()


def _pull_request_from_github(payload: dict[str, Any]) -> ForgePullRequest:
    try:
        return ForgePullRequest.model_validate(
            {
                "number": payload["number"],
                "url": payload["html_url"],
                "head_branch": payload["head"]["ref"],
                "head_sha": payload["head"]["sha"],
                "state": payload["state"],
                "merged": bool(payload.get("merged", False)),
            }
        )
    except (KeyError, TypeError, ValidationError) as error:
        raise IssueRouterError("GitHub returned an invalid pull request") from error


def _all_router_events(project_dir) -> list[dict[str, Any]]:
    events_dir = project_dir / "events"
    if not events_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in events_dir.glob("*.json"):
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(event, dict) and str(event.get("issue_id", "")).startswith(
            "router:"
        ):
            records.append(_decode_router_event(event))
    return sorted(
        records,
        key=lambda item: (
            str(item.get("occurred_at", "")),
            str(item.get("event_id", "")),
        ),
    )
