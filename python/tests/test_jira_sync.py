from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from kanbus import jira_sync
from kanbus.jira_sync import JiraSyncError
from kanbus.models import JiraConfiguration

from test_helpers import build_issue


def _jira_config() -> JiraConfiguration:
    return JiraConfiguration.model_validate(
        {
            "url": "https://jira.example.com",
            "project_key": "KAN",
            "sync_direction": "pull",
            "type_mappings": {"Story": "story"},
            "field_mappings": {},
        }
    )


def _jira_issue(key: str, *, summary: str = "S", parent: str | None = None):
    fields = {
        "summary": summary,
        "description": {
            "type": "doc",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "hardBreak"},
                {"type": "text", "text": "World"},
            ],
        },
        "issuetype": {"name": "Story"},
        "status": {"name": "In Progress"},
        "priority": {"name": "High"},
        "assignee": {"displayName": "Alice"},
        "reporter": {"displayName": "Bob"},
        "labels": ["l1"],
        "comment": {
            "comments": [
                {
                    "id": "10",
                    "author": {"displayName": "Carol"},
                    "body": "plain",
                    "created": "2026-03-09T00:00:00Z",
                }
            ]
        },
        "created": "2026-03-08T00:00:00Z",
        "updated": "2026-03-09T00:00:00Z",
        "resolutiondate": "2026-03-10T00:00:00Z",
    }
    if parent:
        fields["parent"] = {"key": parent}
    return {"key": key, "fields": fields}


def test_pull_from_jira_validates_env_and_project_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _jira_config()

    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.delenv("JIRA_USER_EMAIL", raising=False)

    with pytest.raises(JiraSyncError, match="JIRA_API_TOKEN"):
        jira_sync.pull_from_jira(tmp_path, cfg, "kanbus")

    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    with pytest.raises(JiraSyncError, match="JIRA_USER_EMAIL"):
        jira_sync.pull_from_jira(tmp_path, cfg, "kanbus")

    monkeypatch.setenv("JIRA_USER_EMAIL", "u@example.com")
    monkeypatch.setattr(
        "kanbus.project.load_project_directory",
        lambda _root: tmp_path / "project",
    )
    with pytest.raises(JiraSyncError, match="issues directory does not exist"):
        jira_sync.pull_from_jira(tmp_path, cfg, "kanbus")


def test_pull_from_jira_updates_and_pulls_with_dry_run_and_write_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _jira_config()
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    monkeypatch.setenv("JIRA_USER_EMAIL", "u@example.com")

    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)

    monkeypatch.setattr("kanbus.project.load_project_directory", lambda _root: project_dir)

    issues = [_jira_issue("KAN-1", summary="Existing"), _jira_issue("KAN-2", summary="New", parent="KAN-1")]
    monkeypatch.setattr(jira_sync, "_fetch_all_jira_issues", lambda *_args: issues)

    monkeypatch.setattr(jira_sync, "list_issue_identifiers", lambda _dir: {"kanbus-aaaa111"})
    monkeypatch.setattr(
        jira_sync,
        "_build_jira_key_index",
        lambda _ids, _dir: {"KAN-1": "kanbus-aaaa111"},
    )

    monkeypatch.setattr(
        jira_sync,
        "generate_issue_identifier",
        lambda _req: SimpleNamespace(identifier="kanbus-bbbb222"),
    )
    (issues_dir / "kanbus-aaaa111.json").write_text("{}", encoding="utf-8")

    existing_issue = build_issue("kanbus-aaaa111")
    read_calls: list[Path] = []
    monkeypatch.setattr(jira_sync, "read_issue_from_file", lambda p: read_calls.append(p) or existing_issue)

    writes: list[Path] = []
    monkeypatch.setattr(jira_sync, "write_issue_to_file", lambda issue, path: writes.append(path))

    result_dry = jira_sync.pull_from_jira(tmp_path, cfg, "kanbus", dry_run=True)
    assert result_dry.updated == 1
    assert result_dry.pulled == 1
    assert writes == []

    result = jira_sync.pull_from_jira(tmp_path, cfg, "kanbus", dry_run=False)
    assert result.updated == 1
    assert result.pulled == 1
    assert len(writes) == 2
    assert any(path.name == "kanbus-aaaa111.json" for path in writes)
    assert any(path.name == "kanbus-bbbb222.json" for path in writes)
    assert read_calls

    # Existing read failure should be ignored.
    monkeypatch.setattr(jira_sync, "read_issue_from_file", lambda _p: (_ for _ in ()).throw(RuntimeError("boom")))
    jira_sync.pull_from_jira(tmp_path, cfg, "kanbus", dry_run=True)


def test_fetch_all_jira_issues_pagination_and_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _jira_config()

    class Response:
        def __init__(self, ok: bool, payload: dict, status_code: int = 200, text: str = ""):
            self.ok = ok
            self._payload = payload
            self.status_code = status_code
            self.text = text

        def json(self):
            return self._payload

    calls: list[str] = []

    def fake_get(url, auth, headers, timeout):
        calls.append(url)
        if "startAt=0" in url:
            return Response(True, {"issues": [{"key": "KAN-1"}], "total": 2})
        return Response(True, {"issues": [{"key": "KAN-2"}], "total": 2})

    monkeypatch.setattr(jira_sync.requests, "get", fake_get)
    issues = jira_sync._fetch_all_jira_issues(cfg, "u@example.com", "tok")
    assert [issue["key"] for issue in issues] == ["KAN-1", "KAN-2"]
    assert len(calls) == 2

    monkeypatch.setattr(
        jira_sync.requests,
        "get",
        lambda *args, **kwargs: Response(False, {}, status_code=401, text="unauthorized"),
    )
    with pytest.raises(JiraSyncError, match="Jira API returned 401"):
        jira_sync._fetch_all_jira_issues(cfg, "u@example.com", "tok")


def test_build_jira_key_index_handles_read_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing_ids = {"kanbus-1", "kanbus-2"}

    def fake_read(path: Path):
        if path.name.startswith("kanbus-1"):
            issue = build_issue("kanbus-1")
            issue.custom = {"jira_key": "KAN-1"}
            return issue
        raise RuntimeError("bad")

    monkeypatch.setattr(jira_sync, "read_issue_from_file", fake_read)
    index = jira_sync._build_jira_key_index(existing_ids, tmp_path)
    assert index == {"KAN-1": "kanbus-1"}


def test_jira_key_and_summary_extractors() -> None:
    assert jira_sync._jira_issue_key({"key": "KAN-1"}) == "KAN-1"
    assert jira_sync._jira_issue_key({}) == ""
    assert jira_sync._jira_issue_summary({"fields": {"summary": "S"}}) == "S"
    assert jira_sync._jira_issue_summary({}) == "Untitled"


def test_map_jira_to_kanbus_and_support_helpers() -> None:
    cfg = _jira_config()
    issue = _jira_issue("KAN-1", summary="Story A")
    mapped = jira_sync._map_jira_to_kanbus(issue, cfg, {"KAN-1": "kanbus-1"})

    assert mapped.title == "Story A"
    assert mapped.issue_type == "story"
    assert mapped.status == "in_progress"
    assert mapped.priority == 1
    assert mapped.assignee == "Alice"
    assert mapped.creator == "Bob"
    assert mapped.labels == ["l1"]
    assert mapped.custom["jira_key"] == "KAN-1"
    assert mapped.comments[0].author == "Carol"

    assert jira_sync._extract_adf_text(None) == ""
    assert jira_sync._extract_adf_text("plain") == "plain"
    assert "Hello" in jira_sync._extract_adf_text(issue["fields"]["description"])
    assert jira_sync._extract_adf_text(123) == ""

    assert jira_sync._extract_adf_content({"content": [{"type": "text", "text": "a"}]}) == "a"
    assert (
        jira_sync._extract_adf_content(
            {"content": [{"type": "paragraph", "content": [{"type": "text", "text": "b"}]}]}
        )
        == "b"
    )

    comments = jira_sync._extract_comments(
        {"comments": [{"author": {}, "body": None, "created": "bad-date"}]}
    )
    assert comments[0].author == "Unknown"
    assert comments[0].text == "(empty)"

    assert jira_sync._map_jira_status("To Do") == "open"
    assert jira_sync._map_jira_status("In Development") == "in_progress"
    assert jira_sync._map_jira_status("Resolved") == "closed"
    assert jira_sync._map_jira_status("Blocked") == "blocked"
    assert jira_sync._map_jira_status("SomethingElse") == "open"

    assert jira_sync._map_jira_priority("Highest") == 0
    assert jira_sync._map_jira_priority("High") == 1
    assert jira_sync._map_jira_priority("Normal") == 2
    assert jira_sync._map_jira_priority("Low") == 3
    assert jira_sync._map_jira_priority("Trivial") == 4
    assert jira_sync._map_jira_priority("Unknown") == 2

    dt = jira_sync._parse_jira_datetime("2026-03-09T00:00:00Z")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None
    assert jira_sync._parse_jira_datetime("") is None
    assert jira_sync._parse_jira_datetime(None) is None
    assert jira_sync._parse_jira_datetime("bad") is None

    assert jira_sync.issue_path_for_identifier(Path("/x"), "kanbus-1") == Path("/x/kanbus-1.json")
