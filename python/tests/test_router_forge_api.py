"""Failure and idempotency tests for the GitHub forge boundary."""

from __future__ import annotations

import requests
import pytest

from kanbus.issue_router import IssueRouterError
from kanbus.router_forge import GitHubForge


def _github_pull(number: int = 7) -> dict[str, object]:
    return {
        "number": number,
        "html_url": f"https://github.example/pull/{number}",
        "head": {"ref": "codex/router/kbs-7/r1", "sha": "head-7"},
        "state": "open",
        "merged": False,
    }


def test_pull_request_creation_reuses_existing_branch(monkeypatch):
    forge = GitHubForge(repository="owner/repo", token="secret")
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return [_github_pull()]

    monkeypatch.setattr(forge, "_request", request)
    pull = forge.create_or_observe_pull_request(
        title="router work",
        body="summary",
        head_branch="codex/router/kbs-7/r1",
        base_branch="main",
    )

    assert pull.number == 7
    assert pull.head_sha == "head-7"
    assert len(calls) == 1
    assert calls[0][0:2] == ("GET", "/repos/owner/repo/pulls")
    assert calls[0][2]["params"]["head"] == "owner:codex/router/kbs-7/r1"


def test_pull_request_creation_posts_when_no_existing_branch(monkeypatch):
    forge = GitHubForge(repository="owner/repo", token="secret")
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return [] if method == "GET" else _github_pull(8)

    monkeypatch.setattr(forge, "_request", request)
    pull = forge.create_or_observe_pull_request(
        title="router work",
        body="summary",
        head_branch="codex/router/kbs-7/r1",
        base_branch="trunk",
    )

    assert pull.number == 8
    assert [call[0] for call in calls] == ["GET", "POST"]
    assert calls[1][2]["payload"] == {
        "title": "router work",
        "body": "summary",
        "head": "codex/router/kbs-7/r1",
        "base": "trunk",
    }


def test_github_request_maps_network_http_and_json_errors(monkeypatch):
    forge = GitHubForge(repository="owner/repo", token="not-printable")

    def offline(*_args, **_kwargs):
        raise requests.ConnectionError("credential details must not escape")

    monkeypatch.setattr(requests, "request", offline)
    with pytest.raises(IssueRouterError, match="GitHub API unavailable") as raised:
        forge._request("GET", "/repos/owner/repo/pulls")
    assert "credential details" not in str(raised.value)

    class Response:
        status_code = 403
        content = b"denied"

        def json(self):
            return {"message": "denied"}

    monkeypatch.setattr(requests, "request", lambda *_args, **_kwargs: Response())
    with pytest.raises(IssueRouterError, match="status 403"):
        forge._request("GET", "/repos/owner/repo/pulls")

    class InvalidJsonResponse:
        status_code = 200
        content = b"not-json"

        def json(self):
            raise ValueError("private payload")

    monkeypatch.setattr(
        requests, "request", lambda *_args, **_kwargs: InvalidJsonResponse()
    )
    with pytest.raises(IssueRouterError, match="invalid JSON") as raised:
        forge._request("GET", "/repos/owner/repo/pulls")
    assert "private payload" not in str(raised.value)


def test_pull_request_decoder_rejects_incomplete_api_response(monkeypatch):
    forge = GitHubForge(repository="owner/repo", token="secret")
    monkeypatch.setattr(forge, "_request", lambda *_args, **_kwargs: [{"number": 7}])

    with pytest.raises(IssueRouterError, match="invalid pull request"):
        forge.create_or_observe_pull_request(
            title="router work",
            body="summary",
            head_branch="codex/router/kbs-7/r1",
            base_branch="main",
        )
