from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from types import SimpleNamespace

from kanbus import snyk_sync
from kanbus.issue_files import read_issue_from_file, write_issue_to_file
from kanbus.models import SnykConfiguration
from test_helpers import build_issue


def test_severity_to_priority_mapping() -> None:
    assert snyk_sync._severity_to_priority("critical") == 0
    assert snyk_sync._severity_to_priority("high") == 1
    assert snyk_sync._severity_to_priority("medium") == 2
    assert snyk_sync._severity_to_priority("low") == 3


def test_vuln_title_for_dependency_and_code() -> None:
    dependency_issue = {
        "attributes": {
            "key": "SNYK-001",
            "type": "package_vulnerability",
            "coordinates": [
                {
                    "representations": [
                        {
                            "dependency": {
                                "package_name": "requests",
                                "package_version": "2",
                            }
                        }
                    ]
                }
            ],
        }
    }
    code_issue = {
        "attributes": {
            "key": "SNYK-CODE-001",
            "type": "code",
            "title": "Unsanitized input",
        }
    }

    assert snyk_sync._vuln_title(dependency_issue) == "[Snyk] SNYK-001 in requests"
    assert snyk_sync._vuln_title(code_issue) == "[Snyk Code] Unsanitized input"


def test_vuln_title_dependency_without_package_name() -> None:
    dependency_issue = {
        "attributes": {
            "key": "SNYK-EMPTY",
            "type": "package_vulnerability",
            "coordinates": [{"representations": [{"dependency": {}}]}],
        }
    }
    assert snyk_sync._vuln_title(dependency_issue) == "[Snyk] SNYK-EMPTY"


def test_extract_source_location_handles_region_and_line_column() -> None:
    issue_with_region = {
        "attributes": {
            "coordinates": [
                {
                    "representations": [
                        {
                            "source_location": {
                                "file": "src/main.py",
                                "region": {
                                    "start": {"line": 10, "column": 2},
                                    "end": {"line": 12, "column": 4},
                                },
                            }
                        }
                    ]
                }
            ]
        }
    }
    issue_with_line = {
        "attributes": {
            "coordinates": [
                {
                    "representations": [
                        {
                            "sourceLocation": {
                                "file": "src/legacy.py",
                                "line": 7,
                                "col": 9,
                            }
                        }
                    ]
                }
            ]
        }
    }

    assert snyk_sync._extract_source_location(issue_with_region) == {
        "file": "src/main.py",
        "line": 10,
        "column": 2,
        "end_line": 12,
        "end_column": 4,
    }
    assert snyk_sync._extract_source_location(issue_with_line) == {
        "file": "src/legacy.py",
        "line": 7,
        "column": 9,
    }


def test_build_snippet_renders_context_window(tmp_path: Path) -> None:
    source_file = tmp_path / "src" / "app.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        "\n".join(
            [
                "line 1",
                "line 2",
                "line 3",
                "line 4",
                "line 5",
            ]
        ),
        encoding="utf-8",
    )

    snippet = snyk_sync._build_snippet(tmp_path, "src/app.py", 3, 3)

    assert "### Snippet (src/app.py:1-5)" in snippet
    assert "   3 | line 3" in snippet


def test_build_snippet_returns_empty_for_empty_file(tmp_path: Path) -> None:
    source_file = tmp_path / "src" / "empty.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("", encoding="utf-8")
    assert snyk_sync._build_snippet(tmp_path, "src/empty.py", 1, 1) == ""


def test_map_snyk_to_kanbus_sets_core_custom_fields(tmp_path: Path) -> None:
    issue = {
        "attributes": {
            "key": "SNYK-002",
            "effective_severity_level": "high",
            "type": "package_vulnerability",
            "coordinates": [
                {
                    "is_upgradeable": True,
                    "representations": [
                        {
                            "dependency": {
                                "package_name": "urllib3",
                                "package_version": "1.0.0",
                            }
                        }
                    ],
                }
            ],
            "problems": [{"source": "NVD", "id": "CVE-2026-0001"}],
        }
    }

    mapped = snyk_sync._map_snyk_to_kanbus(
        issue,
        parent_task_id="kanbus-parent",
        target_file="requirements.txt",
        repo_root=tmp_path,
    )

    assert mapped.issue_type == "sub-task"
    assert mapped.priority == 1
    assert mapped.parent == "kanbus-parent"
    assert mapped.custom["snyk_key"] == "SNYK-002"
    assert mapped.custom["snyk_severity"] == "high"


def test_extract_classes_handles_string_and_object_shapes() -> None:
    issue = {
        "attributes": {
            "classes": [
                "OWASP-A1",
                {"source": "CWE", "id": "79"},
                {"source": "CAPEC", "id": "1"},
                {"id": "missing-source"},
            ]
        }
    }
    assert snyk_sync._extract_classes(issue) == [
        "OWASP-A1",
        "CWE-79",
        "CAPEC-1",
    ]


def test_detect_repo_from_git_normalizes_github_remote(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "git@github.com:AnthusAI/Kanbus.git"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert snyk_sync._detect_repo_from_git(tmp_path) == "AnthusAI/Kanbus"


def test_detect_repo_from_git_returns_none_for_non_github_remote(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "ssh://gitlab.example.com/team/repo.git"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert snyk_sync._detect_repo_from_git(tmp_path) is None


class _FakeResponse:
    def __init__(
        self, ok: bool, status_code: int, payload: dict, text: str = ""
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        return self._payload


def test_fetch_snyk_projects_handles_pagination_and_repo_filter(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, headers: dict, timeout: int) -> _FakeResponse:
        calls.append(url)
        if "limit=100" in url:
            return _FakeResponse(
                ok=True,
                status_code=200,
                payload={
                    "data": [
                        {
                            "id": "p1",
                            "attributes": {
                                "name": "AnthusAI/Kanbus:requirements.txt",
                                "target_file": "requirements.txt",
                            },
                        },
                        {
                            "id": "skip",
                            "attributes": {"name": "Other/Repo:package.json"},
                        },
                    ],
                    "links": {"next": "/rest/orgs/org/projects?page=2"},
                },
            )
        return _FakeResponse(
            ok=True,
            status_code=200,
            payload={
                "data": [
                    {
                        "id": "p2",
                        "attributes": {
                            "name": "AnthusAI/Kanbus",
                            "target_file": "repo-root",
                        },
                    }
                ],
                "links": {},
            },
        )

    monkeypatch.setattr(snyk_sync.requests, "get", fake_get)
    project_map = snyk_sync._fetch_snyk_projects(
        org_id="org", token="token", repo_filter="AnthusAI/Kanbus"
    )
    assert project_map == {"p1": "requirements.txt", "p2": "repo-root"}
    assert len(calls) == 2


def test_fetch_snyk_projects_uses_name_when_target_file_missing(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> _FakeResponse:
        return _FakeResponse(
            ok=True,
            status_code=200,
            payload={
                "data": [
                    {
                        "id": "p3",
                        "attributes": {"name": "AnthusAI/Kanbus:pyproject.toml"},
                    }
                ],
                "links": {},
            },
        )

    monkeypatch.setattr(snyk_sync.requests, "get", fake_get)
    project_map = snyk_sync._fetch_snyk_projects(
        org_id="org", token="token", repo_filter="AnthusAI/Kanbus"
    )
    assert project_map == {"p3": "AnthusAI/Kanbus:pyproject.toml"}


def test_fetch_snyk_projects_raises_on_non_ok_response(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> _FakeResponse:
        return _FakeResponse(
            ok=False,
            status_code=403,
            payload={},
            text="forbidden",
        )

    monkeypatch.setattr(snyk_sync.requests, "get", fake_get)
    try:
        snyk_sync._fetch_snyk_projects(org_id="org", token="token", repo_filter=None)
    except snyk_sync.SnykSyncError as error:
        assert "Snyk projects API returned 403" in str(error)
    else:
        raise AssertionError("expected SnykSyncError")


def test_fetch_snyk_issues_for_type_applies_severity_threshold(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> _FakeResponse:
        return _FakeResponse(
            ok=True,
            status_code=200,
            payload={
                "data": [
                    {
                        "attributes": {
                            "key": "S-1",
                            "effective_severity_level": "critical",
                        }
                    },
                    {"attributes": {"key": "S-2", "effective_severity_level": "low"}},
                    {"attributes": {"effective_severity_level": "high"}},
                ],
                "links": {},
            },
        )

    monkeypatch.setattr(snyk_sync.requests, "get", fake_get)
    issues = snyk_sync._fetch_snyk_issues_for_type(
        org_id="org", token="token", min_priority=1, issue_type="code"
    )
    assert [item["attributes"]["key"] for item in issues] == ["S-1"]


def test_fetch_snyk_issues_for_type_raises_on_non_ok(monkeypatch) -> None:
    def fake_get(url: str, headers: dict, timeout: int) -> _FakeResponse:
        return _FakeResponse(ok=False, status_code=502, payload={}, text="gateway")

    monkeypatch.setattr(snyk_sync.requests, "get", fake_get)
    try:
        snyk_sync._fetch_snyk_issues_for_type(
            org_id="org", token="token", min_priority=1, issue_type="code"
        )
    except snyk_sync.SnykSyncError as error:
        assert "Snyk API returned 502" in str(error)
    else:
        raise AssertionError("expected SnykSyncError")


def test_fetch_snyk_issues_for_type_handles_pagination(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(url: str, headers: dict, timeout: int) -> _FakeResponse:
        calls.append(url)
        if len(calls) == 1:
            return _FakeResponse(
                ok=True,
                status_code=200,
                payload={
                    "data": [
                        {
                            "attributes": {
                                "key": "S-1",
                                "effective_severity_level": "high",
                            }
                        }
                    ],
                    "links": {"next": "/rest/orgs/org/issues?page=2"},
                },
            )
        return _FakeResponse(
            ok=True,
            status_code=200,
            payload={
                "data": [
                    {
                        "attributes": {
                            "key": "S-2",
                            "effective_severity_level": "medium",
                        }
                    }
                ],
                "links": {},
            },
        )

    monkeypatch.setattr(snyk_sync.requests, "get", fake_get)
    issues = snyk_sync._fetch_snyk_issues_for_type(
        org_id="org", token="token", min_priority=2, issue_type="code"
    )
    assert [item["attributes"]["key"] for item in issues] == ["S-1", "S-2"]
    assert len(calls) == 2


def test_fetch_all_snyk_issues_continues_when_non_package_type_fails(
    monkeypatch,
) -> None:
    def fake_fetch(org_id: str, token: str, min_priority: int, issue_type: str):
        if issue_type == "package_vulnerability":
            return [{"attributes": {"key": "S-OK"}}]
        raise snyk_sync.SnykSyncError("code endpoint failed")

    monkeypatch.setattr(snyk_sync, "_fetch_snyk_issues_for_type", fake_fetch)
    issues = snyk_sync._fetch_all_snyk_issues(
        org_id="org",
        token="token",
        min_priority=2,
        issue_types=["package_vulnerability", "code"],
    )
    assert [item["attributes"]["key"] for item in issues] == ["S-OK"]


def test_fetch_all_snyk_issues_raises_when_package_type_fails(monkeypatch) -> None:
    def fake_fetch(org_id: str, token: str, min_priority: int, issue_type: str):
        raise snyk_sync.SnykSyncError(f"{issue_type} failed")

    monkeypatch.setattr(snyk_sync, "_fetch_snyk_issues_for_type", fake_fetch)
    try:
        snyk_sync._fetch_all_snyk_issues(
            org_id="org",
            token="token",
            min_priority=2,
            issue_types=["package_vulnerability", "code"],
        )
    except snyk_sync.SnykSyncError as error:
        assert "package_vulnerability failed" in str(error)
    else:
        raise AssertionError("expected SnykSyncError")


def test_fetch_v1_enrichment_skips_non_ok_and_uses_issue_id(monkeypatch) -> None:
    def fake_post(url: str, headers: dict, json: dict, timeout: int) -> _FakeResponse:
        if "project-a" in url:
            return _FakeResponse(ok=False, status_code=500, payload={}, text="fail")
        return _FakeResponse(
            ok=True,
            status_code=200,
            payload={"issues": [{"issueData": {"id": "SNYK-1"}, "fixInfo": {}}]},
        )

    monkeypatch.setattr(snyk_sync.requests, "post", fake_post)
    enriched = snyk_sync._fetch_v1_enrichment(
        org_id="org",
        token="token",
        project_ids=["project-a", "project-b"],
    )
    assert "SNYK-1" in enriched


def test_fetch_v1_enrichment_continues_when_request_raises(monkeypatch) -> None:
    calls = {"count": 0}

    def fake_post(url: str, headers: dict, json: dict, timeout: int) -> _FakeResponse:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("network failure")
        return _FakeResponse(
            ok=True,
            status_code=200,
            payload={"issues": [{"issueData": {"id": "SNYK-2"}}]},
        )

    monkeypatch.setattr(snyk_sync.requests, "post", fake_post)
    enriched = snyk_sync._fetch_v1_enrichment(
        org_id="org",
        token="token",
        project_ids=["project-a", "project-b"],
    )
    assert enriched == {"SNYK-2": {"issueData": {"id": "SNYK-2"}}}


def test_map_snyk_to_kanbus_code_includes_location_custom_fields(
    tmp_path: Path,
) -> None:
    source_file = tmp_path / "src" / "vuln.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")

    issue = {
        "attributes": {
            "key": "SNYK-CODE-42",
            "type": "code",
            "title": "Unsafely parsed input",
            "description": "User-controlled input is parsed without validation.",
            "effective_severity_level": "medium",
            "coordinates": [
                {
                    "representations": [
                        {
                            "source_location": {
                                "file": "src/vuln.py",
                                "region": {
                                    "start": {"line": 2, "column": 3},
                                    "end": {"line": 3, "column": 5},
                                },
                            }
                        }
                    ]
                }
            ],
            "classes": [{"source": "CWE", "id": "20"}],
        }
    }

    mapped = snyk_sync._map_snyk_to_kanbus(
        issue,
        parent_task_id="KAN-100",
        target_file="repo",
        repo_root=tmp_path,
    )

    assert mapped.title == "[Snyk Code] Unsafely parsed input"
    assert mapped.custom["snyk_file"] == "src/vuln.py"
    assert mapped.custom["snyk_line"] == 2
    assert mapped.custom["snyk_column"] == 3
    assert mapped.custom["snyk_end_line"] == 3
    assert mapped.custom["snyk_end_column"] == 5
    assert "**Classes:** CWE-20" in mapped.description
    assert "### Snippet (src/vuln.py:1-5)" in mapped.description


def test_map_snyk_to_kanbus_dependency_uses_v1_fix_and_meta() -> None:
    issue = {
        "attributes": {
            "key": "SNYK-DEP-99",
            "type": "package_vulnerability",
            "effective_severity_level": "high",
            "coordinates": [
                {
                    "is_upgradeable": True,
                    "representations": [
                        {
                            "dependency": {
                                "package_name": "openssl",
                                "package_version": "1.0.2",
                            }
                        }
                    ],
                }
            ],
            "problems": [
                {"source": "NVD", "id": "CVE-2026-1111"},
                {"source": "NVD", "id": "CVE-2026-2222"},
            ],
        }
    }
    v1 = {
        "issueData": {
            "title": "OpenSSL out-of-bounds read",
            "description": "Detailed advisory text",
            "cvssScore": 9.7,
            "exploitMaturity": "proof-of-concept",
        },
        "priorityScore": 860,
        "fixInfo": {"fixedIn": ["1.1.1u"]},
    }

    mapped = snyk_sync._map_snyk_to_kanbus(
        issue,
        parent_task_id="KAN-200",
        v1=v1,
        target_file="requirements.txt",
    )

    assert mapped.title == "[Snyk] SNYK-DEP-99 in openssl@1.0.2"
    assert "## OpenSSL out-of-bounds read" in mapped.description
    assert "**CVSS Score:** 9.7" in mapped.description
    assert "**Exploit Maturity:** proof-of-concept" in mapped.description
    assert "**Snyk Priority Score:** 860/1000" in mapped.description
    assert "Upgrade `openssl` to version 1.1.1u or later." in mapped.description
    assert "CVE-2026-1111" in mapped.description
    assert "CVE-2026-2222" in mapped.description


def _write_issue(issues_dir: Path, issue) -> None:
    write_issue_to_file(issue, issues_dir / f"{issue.identifier}.json")


def test_pull_from_snyk_requires_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SNYK_TOKEN", raising=False)
    config = SnykConfiguration.model_validate({"org_id": "org"})
    try:
        snyk_sync.pull_from_snyk(tmp_path, config, "kanbus")
    except snyk_sync.SnykSyncError as error:
        assert "SNYK_TOKEN environment variable is not set" in str(error)
    else:
        raise AssertionError("expected SnykSyncError")


def test_resolve_snyk_epics_returns_empty_when_no_categories(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    epics = snyk_sync._resolve_snyk_epics(
        issues_dir=issues_dir,
        project_key="kanbus",
        configured_id=None,
        dry_run=False,
        all_existing=set(),
        include_dependency=False,
        include_code=False,
        dependency_priority=None,
        code_priority=None,
    )
    assert epics == {}


def test_find_existing_snyk_initiative_prefers_most_recent(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    older = build_issue(
        "kanbus-1",
        issue_type="initiative",
        title=snyk_sync.SNYK_INITIATIVE_TITLE,
        labels=["snyk"],
    )
    newer = build_issue(
        "kanbus-2",
        issue_type="initiative",
        title=snyk_sync.SNYK_INITIATIVE_TITLE,
        labels=["snyk"],
    )
    older.updated_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    newer.updated_at = datetime(2026, 3, 2, tzinfo=timezone.utc)
    _write_issue(issues_dir, older)
    _write_issue(issues_dir, newer)

    found = snyk_sync._find_existing_snyk_initiative(
        issues_dir, {"kanbus-1", "kanbus-2"}
    )
    assert found == "kanbus-2"


def test_resolve_snyk_epic_updates_existing_priority(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    existing = build_issue(
        "kanbus-epic",
        issue_type="epic",
        title=snyk_sync.SNYK_DEP_EPIC_TITLE,
        parent="kanbus-init",
        priority=3,
        labels=["snyk", "security", "dependency"],
    )
    _write_issue(issues_dir, existing)
    all_existing = {"kanbus-epic"}

    epic_id = snyk_sync._resolve_snyk_epic(
        issues_dir=issues_dir,
        project_key="kanbus",
        parent_initiative="kanbus-init",
        title=snyk_sync.SNYK_DEP_EPIC_TITLE,
        category="dependency",
        priority=1,
        dry_run=False,
        all_existing=all_existing,
    )
    assert epic_id == "kanbus-epic"
    updated = read_issue_from_file(issues_dir / "kanbus-epic.json")
    assert updated.priority == 1


def test_resolve_file_task_updates_existing_task(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    task = build_issue(
        "kanbus-task",
        issue_type="task",
        title="requirements.txt",
        parent="kanbus-old-epic",
        priority=3,
        labels=[],
        custom={"snyk_target_file": "requirements.txt"},
    )
    task.updated_at = datetime.now(timezone.utc) - timedelta(days=2)
    _write_issue(issues_dir, task)

    task_id = snyk_sync._resolve_file_task(
        issues_dir=issues_dir,
        project_key="kanbus",
        target_file="requirements.txt",
        category="dependency",
        ctx=snyk_sync.FileTaskContext(
            epic_id="kanbus-new-epic",
            priority=1,
            dry_run=False,
        ),
        file_task_index={("dependency", "requirements.txt"): "kanbus-task"},
        all_existing={"kanbus-task"},
    )

    assert task_id == "kanbus-task"
    updated = read_issue_from_file(issues_dir / "kanbus-task.json")
    assert updated.parent == "kanbus-new-epic"
    assert updated.priority == 1
    assert "snyk" in updated.labels
    assert "security" in updated.labels
    assert updated.custom["snyk_target_file"] == "requirements.txt"
    assert updated.custom["snyk_category"] == "dependency"


def test_resolve_parent_epic_prefers_configured_existing_id(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    configured = build_issue("kanbus-configured", issue_type="epic", labels=["snyk"])
    _write_issue(issues_dir, configured)

    resolved = snyk_sync._resolve_parent_epic(
        issues_dir=issues_dir,
        project_key="kanbus",
        configured_id="kanbus-configured",
        dry_run=False,
        all_existing={"kanbus-configured"},
    )
    assert resolved == "kanbus-configured"


def test_resolve_parent_epic_reuses_existing_snyk_epic(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    existing = build_issue(
        "kanbus-existing",
        issue_type="epic",
        title="Snyk Vulnerabilities",
        labels=["security", "snyk"],
    )
    _write_issue(issues_dir, existing)

    resolved = snyk_sync._resolve_parent_epic(
        issues_dir=issues_dir,
        project_key="kanbus",
        configured_id=None,
        dry_run=False,
        all_existing={"kanbus-existing"},
    )
    assert resolved == "kanbus-existing"


def test_build_snyk_key_index_and_file_task_index_skip_invalid_issue_files(
    tmp_path: Path,
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    with_key = build_issue(
        "kanbus-key",
        issue_type="sub-task",
        custom={"snyk_key": "SNYK-INDEX-1"},
    )
    with_task = build_issue(
        "kanbus-task",
        issue_type="task",
        custom={"snyk_target_file": "requirements.txt", "snyk_category": "dependency"},
    )
    _write_issue(issues_dir, with_key)
    _write_issue(issues_dir, with_task)
    (issues_dir / "broken.json").write_text("{", encoding="utf-8")

    key_index = snyk_sync._build_snyk_key_index(
        {"kanbus-key", "kanbus-task", "broken"}, issues_dir
    )
    file_index = snyk_sync._build_file_task_index(
        {"kanbus-key", "kanbus-task", "broken"}, issues_dir
    )

    assert key_index["SNYK-INDEX-1"] == "kanbus-key"
    assert file_index[("dependency", "requirements.txt")] == "kanbus-task"


def test_resolve_snyk_epics_with_configured_parent_maps_requested_categories(
    tmp_path: Path, monkeypatch
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    calls: list[tuple[bool, bool]] = []
    monkeypatch.setattr(
        snyk_sync,
        "_resolve_parent_epic",
        lambda *args, **kwargs: (calls.append((True, True)) or "kanbus-parent"),
    )
    epics = snyk_sync._resolve_snyk_epics(
        issues_dir=issues_dir,
        project_key="kanbus",
        configured_id="kanbus-parent",
        dry_run=False,
        all_existing=set(),
        include_dependency=True,
        include_code=False,
        dependency_priority=1,
        code_priority=2,
    )
    assert epics == {"dependency": "kanbus-parent"}
    assert len(calls) == 1


def test_resolve_parent_epic_creates_new_epic_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    monkeypatch.setattr(
        snyk_sync,
        "generate_issue_identifier",
        lambda request: SimpleNamespace(identifier="kanbus-parent-1"),
    )
    epic_id = snyk_sync._resolve_parent_epic(
        issues_dir=issues_dir,
        project_key="kanbus",
        configured_id=None,
        dry_run=False,
        all_existing=set(),
    )
    assert epic_id == "kanbus-parent-1"
    written = read_issue_from_file(issues_dir / "kanbus-parent-1.json")
    assert written.issue_type == "epic"
    assert written.title == "Snyk Vulnerabilities"


def test_resolve_snyk_epics_creates_initiative_and_both_epics(
    tmp_path: Path, monkeypatch
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    sequence = iter(
        [
            "kanbus-init-1",
            "kanbus-dep-1",
            "kanbus-code-1",
        ]
    )
    monkeypatch.setattr(
        snyk_sync,
        "generate_issue_identifier",
        lambda request: SimpleNamespace(identifier=next(sequence)),
    )
    epics = snyk_sync._resolve_snyk_epics(
        issues_dir=issues_dir,
        project_key="kanbus",
        configured_id=None,
        dry_run=False,
        all_existing=set(),
        include_dependency=True,
        include_code=True,
        dependency_priority=None,
        code_priority=None,
    )
    assert epics == {"dependency": "kanbus-dep-1", "code": "kanbus-code-1"}
    assert (
        read_issue_from_file(issues_dir / "kanbus-init-1.json").issue_type
        == "initiative"
    )
    assert (
        read_issue_from_file(issues_dir / "kanbus-dep-1.json").parent == "kanbus-init-1"
    )
    assert (
        read_issue_from_file(issues_dir / "kanbus-code-1.json").parent
        == "kanbus-init-1"
    )


def test_find_existing_snyk_initiative_and_epic_filters_non_matching(
    tmp_path: Path,
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    wrong_type = build_issue(
        "kanbus-x",
        issue_type="task",
        title=snyk_sync.SNYK_INITIATIVE_TITLE,
        labels=["snyk"],
    )
    wrong_title = build_issue(
        "kanbus-y",
        issue_type="initiative",
        title="Other title",
        labels=["snyk"],
    )
    right_init = build_issue(
        "kanbus-z",
        issue_type="initiative",
        title=snyk_sync.SNYK_INITIATIVE_TITLE,
        labels=["snyk"],
    )
    wrong_parent_epic = build_issue(
        "kanbus-epic-wrong",
        issue_type="epic",
        title=snyk_sync.SNYK_DEP_EPIC_TITLE,
        parent="other-parent",
        labels=["snyk"],
    )
    right_epic = build_issue(
        "kanbus-epic-right",
        issue_type="epic",
        title=snyk_sync.SNYK_DEP_EPIC_TITLE,
        parent="kanbus-z",
        labels=["snyk", "security"],
    )
    for issue in [wrong_type, wrong_title, right_init, wrong_parent_epic, right_epic]:
        _write_issue(issues_dir, issue)
    all_ids = {
        "kanbus-x",
        "kanbus-y",
        "kanbus-z",
        "kanbus-epic-wrong",
        "kanbus-epic-right",
    }
    assert snyk_sync._find_existing_snyk_initiative(issues_dir, all_ids) == "kanbus-z"
    assert (
        snyk_sync._find_existing_snyk_epic(
            issues_dir, all_ids, snyk_sync.SNYK_DEP_EPIC_TITLE, "kanbus-z"
        )
        == "kanbus-epic-right"
    )


def test_resolve_file_task_creates_new_task_and_dry_run_skip_write(
    tmp_path: Path, monkeypatch
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    next_id = {"value": 0}

    def _next_identifier(_request):
        next_id["value"] += 1
        return SimpleNamespace(identifier=f"kanbus-task-new-{next_id['value']}")

    monkeypatch.setattr(
        snyk_sync,
        "generate_issue_identifier",
        _next_identifier,
    )
    created = snyk_sync._resolve_file_task(
        issues_dir=issues_dir,
        project_key="kanbus",
        target_file="package.json",
        category="code",
        ctx=snyk_sync.FileTaskContext(epic_id="kanbus-epic", priority=1, dry_run=False),
        file_task_index={},
        all_existing=set(),
    )
    assert created == "kanbus-task-new-1"
    assert (
        read_issue_from_file(issues_dir / "kanbus-task-new-1.json").issue_type == "task"
    )

    dry_created = snyk_sync._resolve_file_task(
        issues_dir=issues_dir,
        project_key="kanbus",
        target_file="requirements.in",
        category="dependency",
        ctx=snyk_sync.FileTaskContext(epic_id="kanbus-epic", priority=2, dry_run=True),
        file_task_index={},
        all_existing=set(),
    )
    assert dry_created == "kanbus-task-new-2"
    assert not (issues_dir / "kanbus-task-new-2.json").exists()


def test_detect_repo_from_git_https_and_exception(tmp_path: Path, monkeypatch) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/AnthusAI/Kanbus.git"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert snyk_sync._detect_repo_from_git(tmp_path) == "AnthusAI/Kanbus"

    monkeypatch.setattr(
        snyk_sync.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert snyk_sync._detect_repo_from_git(tmp_path) is None


def test_build_file_task_index_defaults_missing_category_to_dependency(
    tmp_path: Path,
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    task = build_issue(
        "kanbus-task-default",
        issue_type="task",
        custom={"snyk_target_file": "pom.xml"},
    )
    _write_issue(issues_dir, task)
    index = snyk_sync._build_file_task_index({"kanbus-task-default"}, issues_dir)
    assert index[("dependency", "pom.xml")] == "kanbus-task-default"


def test_extract_source_location_and_classes_cover_skip_paths() -> None:
    no_loc_issue = {"attributes": {"coordinates": [{"representations": [{"x": 1}]}]}}
    missing_file_issue = {
        "attributes": {"coordinates": [{"representations": [{"source_location": {}}]}]}
    }
    assert snyk_sync._extract_source_location(no_loc_issue) is None
    assert snyk_sync._extract_source_location(missing_file_issue) is None

    classes_issue = {"attributes": {"classes": [{"source": "CWE"}]}}
    assert snyk_sync._extract_classes(classes_issue) == []


def test_build_snippet_handles_io_error_and_max_window(
    tmp_path: Path, monkeypatch
) -> None:
    src = tmp_path / "src" / "many.txt"
    src.parent.mkdir(parents=True)
    src.write_text("\n".join(f"line {idx}" for idx in range(1, 200)), encoding="utf-8")
    snippet = snyk_sync._build_snippet(tmp_path, "src/many.txt", 100, 160)
    assert "### Snippet (src/many.txt:" in snippet
    assert snippet.count("\n") < 60

    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, encoding=None: (_ for _ in ()).throw(OSError("denied")),
    )
    assert snyk_sync._build_snippet(tmp_path, "src/many.txt", 10, 10) == ""


def test_map_snyk_to_kanbus_covers_code_line_only_and_dependency_fix_variants() -> None:
    code_issue = {
        "attributes": {
            "key": "SNYK-CODE-LINE",
            "type": "code",
            "title": "Potential issue",
            "coordinates": [
                {
                    "representations": [
                        {"source_location": {"file": "src/app.py", "line": 10}}
                    ]
                }
            ],
        }
    }
    mapped_code = snyk_sync._map_snyk_to_kanbus(
        code_issue, parent_task_id="KAN-CODE", target_file="repo"
    )
    assert "**Location:** line 10" in mapped_code.description

    dep_issue = {
        "attributes": {
            "key": "SNYK-DEP-FIX",
            "type": "package_vulnerability",
            "effective_severity_level": "low",
            "coordinates": [
                {
                    "is_upgradeable": False,
                    "is_pinnable": True,
                    "is_fixable_snyk": False,
                    "representations": [
                        {
                            "dependency": {
                                "package_name": "pkg",
                                "package_version": "1.0",
                            }
                        }
                    ],
                }
            ],
            "problems": [],
        }
    }
    mapped_pin = snyk_sync._map_snyk_to_kanbus(dep_issue, parent_task_id="KAN-DEP")
    assert "Pin `pkg` to a patched version." in mapped_pin.description

    dep_issue["attributes"]["coordinates"][0]["is_pinnable"] = False
    dep_issue["attributes"]["coordinates"][0]["is_fixable_snyk"] = True
    mapped_fix = snyk_sync._map_snyk_to_kanbus(dep_issue, parent_task_id="KAN-DEP")
    assert "Snyk fix available" in mapped_fix.description

    dep_issue["attributes"]["coordinates"][0]["is_fixable_snyk"] = False
    mapped_manual = snyk_sync._map_snyk_to_kanbus(dep_issue, parent_task_id="KAN-DEP")
    assert "No automatic fix available" in mapped_manual.description

    dep_issue_fixed = {
        "attributes": {
            "key": "SNYK-DEP-FIXED",
            "type": "package_vulnerability",
            "effective_severity_level": "high",
            "coordinates": [
                {
                    "is_upgradeable": False,
                    "representations": [
                        {
                            "dependency": {
                                "package_name": "openssl",
                                "package_version": "1.0",
                            }
                        }
                    ],
                }
            ],
            "problems": [],
        }
    }
    mapped_fixed = snyk_sync._map_snyk_to_kanbus(
        dep_issue_fixed,
        parent_task_id="KAN-DEP",
        v1={"fixInfo": {"fixedIn": ["1.2.3"]}},
    )
    assert "Pin `openssl` to version 1.2.3 or later." in mapped_fixed.description


def test_build_snippet_returns_empty_for_missing_start_and_sets_end_from_start(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src" / "short.txt"
    src.parent.mkdir(parents=True)
    src.write_text("a\nb\nc\n", encoding="utf-8")
    assert snyk_sync._build_snippet(tmp_path, "src/short.txt", None, 2) == ""
    snippet = snyk_sync._build_snippet(tmp_path, "src/short.txt", 2, 0)
    assert "src/short.txt" in snippet


def test_extract_source_location_skips_rep_with_missing_file_after_loc() -> None:
    issue = {
        "attributes": {
            "coordinates": [
                {
                    "representations": [
                        {"source_location": {"line": 7}},
                        {"source_location": {"file": "src/a.py", "line": 8}},
                    ]
                }
            ]
        }
    }
    loc = snyk_sync._extract_source_location(issue)
    assert loc is not None
    assert loc["file"] == "src/a.py"


def test_map_snyk_to_kanbus_code_location_with_column_without_end() -> None:
    issue = {
        "attributes": {
            "key": "SNYK-CODE-COL",
            "type": "code",
            "title": "Column case",
            "coordinates": [
                {
                    "representations": [
                        {
                            "source_location": {
                                "file": "src/code.py",
                                "line": 12,
                                "column": 4,
                            }
                        }
                    ]
                }
            ],
        }
    }
    mapped = snyk_sync._map_snyk_to_kanbus(issue, parent_task_id="KAN-CODE")
    assert "line 12, column 4" in mapped.description


def test_resolve_snyk_epics_configured_parent_supports_code_only(
    tmp_path: Path, monkeypatch
) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    monkeypatch.setattr(
        snyk_sync,
        "_resolve_parent_epic",
        lambda *args, **kwargs: "kanbus-parent",
    )
    epics = snyk_sync._resolve_snyk_epics(
        issues_dir=issues_dir,
        project_key="kanbus",
        configured_id="kanbus-parent",
        dry_run=False,
        all_existing=set(),
        include_dependency=False,
        include_code=True,
        dependency_priority=2,
        code_priority=1,
    )
    assert epics == {"code": "kanbus-parent"}


def test_resolve_snyk_initiative_returns_existing_without_write(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    existing = build_issue(
        "kanbus-init-existing",
        issue_type="initiative",
        title=snyk_sync.SNYK_INITIATIVE_TITLE,
        labels=["snyk"],
    )
    _write_issue(issues_dir, existing)
    resolved = snyk_sync._resolve_snyk_initiative(
        issues_dir=issues_dir,
        project_key="kanbus",
        dry_run=False,
        all_existing={"kanbus-init-existing"},
    )
    assert resolved == "kanbus-init-existing"


def test_find_existing_filters_for_snyk_labels(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    initiative = build_issue(
        "kanbus-init-no-label",
        issue_type="initiative",
        title=snyk_sync.SNYK_INITIATIVE_TITLE,
        labels=[],
    )
    epic = build_issue(
        "kanbus-epic-no-label",
        issue_type="epic",
        title=snyk_sync.SNYK_DEP_EPIC_TITLE,
        parent="kanbus-parent",
        labels=[],
    )
    _write_issue(issues_dir, initiative)
    _write_issue(issues_dir, epic)
    assert (
        snyk_sync._find_existing_snyk_initiative(issues_dir, {"kanbus-init-no-label"})
        is None
    )
    assert (
        snyk_sync._find_existing_snyk_epic(
            issues_dir,
            {"kanbus-epic-no-label"},
            snyk_sync.SNYK_DEP_EPIC_TITLE,
            "kanbus-parent",
        )
        is None
    )


def test_find_existing_parent_epic_filters_non_matching_rows(tmp_path: Path) -> None:
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    non_epic = build_issue(
        "kanbus-task",
        issue_type="task",
        title="Snyk Vulnerabilities",
        labels=["snyk"],
    )
    wrong_title = build_issue(
        "kanbus-epic-wrong-title",
        issue_type="epic",
        title="Different title",
        labels=["snyk"],
    )
    wrong_label = build_issue(
        "kanbus-epic-wrong-label",
        issue_type="epic",
        title="Snyk Vulnerabilities",
        labels=["security"],
    )
    for issue in [non_epic, wrong_title, wrong_label]:
        _write_issue(issues_dir, issue)
    assert (
        snyk_sync._find_existing_parent_epic(
            issues_dir,
            {"kanbus-task", "kanbus-epic-wrong-title", "kanbus-epic-wrong-label"},
        )
        is None
    )


def test_pull_from_snyk_missing_issues_dir_raises(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SNYK_TOKEN", "token")
    config = SnykConfiguration.model_validate({"org_id": "org"})
    import kanbus.project as project_module

    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True)
    monkeypatch.setattr(
        project_module, "load_project_directory", lambda root: project_dir
    )
    try:
        snyk_sync.pull_from_snyk(tmp_path, config, "kanbus")
    except snyk_sync.SnykSyncError as error:
        assert "issues directory does not exist" in str(error)
    else:
        raise AssertionError("expected SnykSyncError")


def test_pull_from_snyk_updated_path_and_skip_missing_project_map(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    monkeypatch.setenv("SNYK_TOKEN", "token")

    import kanbus.project as project_module

    monkeypatch.setattr(
        project_module, "load_project_directory", lambda root: project_dir
    )
    monkeypatch.setattr(
        snyk_sync, "_detect_repo_from_git", lambda root: "AnthusAI/Kanbus"
    )
    monkeypatch.setattr(
        snyk_sync,
        "_fetch_snyk_projects",
        lambda org_id, token, repo_filter: {"p1": "requirements.txt"},
    )
    monkeypatch.setattr(
        snyk_sync,
        "_fetch_all_snyk_issues",
        lambda org_id, token, min_priority, issue_types: [
            {
                "relationships": {"scan_item": {"data": {"id": "missing-project"}}},
                "attributes": {
                    "key": "SNYK-SKIP-1",
                    "type": "package_vulnerability",
                    "effective_severity_level": "low",
                },
            },
            {
                "relationships": {"scan_item": {"data": {"id": "p1"}}},
                "attributes": {
                    "key": "SNYK-UPD-1",
                    "type": "package_vulnerability",
                    "effective_severity_level": "high",
                },
            },
        ],
    )
    monkeypatch.setattr(
        snyk_sync, "_fetch_v1_enrichment", lambda org_id, token, project_ids: {}
    )
    monkeypatch.setattr(
        snyk_sync,
        "_resolve_snyk_epics",
        lambda *args, **kwargs: {"dependency": "kanbus-epic"},
    )
    monkeypatch.setattr(
        snyk_sync,
        "_build_snyk_key_index",
        lambda *_args: {"SNYK-UPD-1": "kanbus-existing-1"},
    )
    monkeypatch.setattr(snyk_sync, "_build_file_task_index", lambda *_args: {})
    monkeypatch.setattr(
        snyk_sync,
        "_resolve_file_task",
        lambda *args, **kwargs: "kanbus-task-dep",
    )
    monkeypatch.setattr(
        snyk_sync,
        "_map_snyk_to_kanbus",
        lambda vuln, task_id, v1_data, target_file, root: build_issue(
            "__placeholder__",
            title="Updated vuln",
            issue_type="sub-task",
            parent=task_id,
            custom={"snyk_key": vuln["attributes"]["key"]},
        ),
    )
    existing = build_issue("kanbus-existing-1", issue_type="sub-task")
    _write_issue(issues_dir, existing)

    def _read_issue_fail(path: Path):
        if path.name == "kanbus-existing-1.json":
            raise RuntimeError("read failed")
        return read_issue_from_file(path)

    monkeypatch.setattr(snyk_sync, "read_issue_from_file", _read_issue_fail)
    writes: list[Path] = []
    monkeypatch.setattr(
        snyk_sync,
        "write_issue_to_file",
        lambda issue, issue_path: writes.append(issue_path),
    )

    config = SnykConfiguration.model_validate({"org_id": "org", "min_severity": "low"})
    result = snyk_sync.pull_from_snyk(tmp_path, config, "kanbus", dry_run=False)
    assert result.updated == 1
    assert result.pulled == 0
    assert len(writes) == 1
    assert "Warning: failed to read existing issue file" in capsys.readouterr().out


def test_pull_from_snyk_skips_when_no_epic_for_category(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    monkeypatch.setenv("SNYK_TOKEN", "token")

    import kanbus.project as project_module

    monkeypatch.setattr(
        project_module, "load_project_directory", lambda root: project_dir
    )
    monkeypatch.setattr(
        snyk_sync, "_detect_repo_from_git", lambda root: "AnthusAI/Kanbus"
    )
    monkeypatch.setattr(
        snyk_sync,
        "_fetch_snyk_projects",
        lambda org_id, token, repo_filter: {"p1": "requirements.txt"},
    )
    monkeypatch.setattr(
        snyk_sync,
        "_fetch_all_snyk_issues",
        lambda org_id, token, min_priority, issue_types: [
            {
                "relationships": {"scan_item": {"data": {"id": "p1"}}},
                "attributes": {
                    "key": "SNYK-NO-EPIC",
                    "type": "package_vulnerability",
                    "effective_severity_level": "high",
                },
            }
        ],
    )
    monkeypatch.setattr(snyk_sync, "_fetch_v1_enrichment", lambda *_args: {})
    monkeypatch.setattr(snyk_sync, "_resolve_snyk_epics", lambda *args, **kwargs: {})
    monkeypatch.setattr(snyk_sync, "_build_snyk_key_index", lambda *_args: {})
    monkeypatch.setattr(snyk_sync, "_build_file_task_index", lambda *_args: {})
    called = {"resolve_task": 0, "write": 0}
    monkeypatch.setattr(
        snyk_sync,
        "_resolve_file_task",
        lambda *args, **kwargs: called.__setitem__(
            "resolve_task", called["resolve_task"] + 1
        ),
    )
    monkeypatch.setattr(
        snyk_sync,
        "write_issue_to_file",
        lambda *args, **kwargs: called.__setitem__("write", called["write"] + 1),
    )
    config = SnykConfiguration.model_validate({"org_id": "org"})
    result = snyk_sync.pull_from_snyk(tmp_path, config, "kanbus", dry_run=False)
    assert result.pulled == 0
    assert result.updated == 0
    assert called["resolve_task"] == 0
    assert called["write"] == 0


def test_pull_from_snyk_updated_path_preserves_created_at_when_existing_readable(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    monkeypatch.setenv("SNYK_TOKEN", "token")

    import kanbus.project as project_module

    monkeypatch.setattr(
        project_module, "load_project_directory", lambda root: project_dir
    )
    monkeypatch.setattr(
        snyk_sync, "_detect_repo_from_git", lambda root: "AnthusAI/Kanbus"
    )
    monkeypatch.setattr(
        snyk_sync,
        "_fetch_snyk_projects",
        lambda org_id, token, repo_filter: {"p1": "requirements.txt"},
    )
    monkeypatch.setattr(
        snyk_sync,
        "_fetch_all_snyk_issues",
        lambda org_id, token, min_priority, issue_types: [
            {
                "relationships": {"scan_item": {"data": {"id": "p1"}}},
                "attributes": {
                    "key": "SNYK-UPD-READ",
                    "type": "package_vulnerability",
                    "effective_severity_level": "high",
                },
            }
        ],
    )
    monkeypatch.setattr(snyk_sync, "_fetch_v1_enrichment", lambda *_args: {})
    monkeypatch.setattr(
        snyk_sync,
        "_resolve_snyk_epics",
        lambda *args, **kwargs: {"dependency": "kanbus-epic"},
    )
    monkeypatch.setattr(
        snyk_sync,
        "_build_snyk_key_index",
        lambda *_args: {"SNYK-UPD-READ": "kanbus-existing-2"},
    )
    monkeypatch.setattr(snyk_sync, "_build_file_task_index", lambda *_args: {})
    monkeypatch.setattr(
        snyk_sync,
        "_resolve_file_task",
        lambda *args, **kwargs: "kanbus-task",
    )
    monkeypatch.setattr(
        snyk_sync,
        "_map_snyk_to_kanbus",
        lambda vuln, task_id, v1_data, target_file, root: build_issue(
            "__placeholder__",
            title="Updated readable",
            issue_type="sub-task",
            parent=task_id,
            custom={"snyk_key": vuln["attributes"]["key"]},
        ),
    )
    existing = build_issue("kanbus-existing-2", issue_type="sub-task")
    existing.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _write_issue(issues_dir, existing)
    written: dict[str, object] = {}

    def _capture_write(issue, issue_path):
        written["created_at"] = issue.created_at
        written["path"] = issue_path

    monkeypatch.setattr(snyk_sync, "write_issue_to_file", _capture_write)
    config = SnykConfiguration.model_validate({"org_id": "org"})
    result = snyk_sync.pull_from_snyk(tmp_path, config, "kanbus", dry_run=False)
    assert result.updated == 1
    assert written["path"].name == "kanbus-existing-2.json"
    assert written["created_at"] == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_pull_from_snyk_groups_dedups_and_writes_issues(
    tmp_path: Path, monkeypatch
) -> None:
    project_dir = tmp_path / "project"
    issues_dir = project_dir / "issues"
    issues_dir.mkdir(parents=True)
    monkeypatch.setenv("SNYK_TOKEN", "token")

    import kanbus.project as project_module

    monkeypatch.setattr(
        project_module, "load_project_directory", lambda root: project_dir
    )
    monkeypatch.setattr(
        snyk_sync, "_detect_repo_from_git", lambda root: "AnthusAI/Kanbus"
    )
    monkeypatch.setattr(
        snyk_sync,
        "_fetch_snyk_projects",
        lambda org_id, token, repo_filter: {
            "p1": "requirements.txt",
            "p2": "src/app.py",
        },
    )
    monkeypatch.setattr(
        snyk_sync,
        "_fetch_all_snyk_issues",
        lambda org_id, token, min_priority, issue_types: [
            {
                "relationships": {"scan_item": {"data": {"id": "p1"}}},
                "attributes": {
                    "key": "SNYK-DEP-1",
                    "type": "package_vulnerability",
                    "effective_severity_level": "high",
                },
            },
            {
                "relationships": {"scan_item": {"data": {"id": "p1"}}},
                "attributes": {
                    "key": "SNYK-DEP-1",
                    "type": "package_vulnerability",
                    "effective_severity_level": "high",
                },
            },
            {
                "relationships": {"scan_item": {"data": {"id": "p2"}}},
                "attributes": {
                    "key": "SNYK-CODE-1",
                    "type": "code",
                    "effective_severity_level": "medium",
                },
            },
        ],
    )
    monkeypatch.setattr(
        snyk_sync, "_fetch_v1_enrichment", lambda org_id, token, project_ids: {}
    )

    epics_calls: list[tuple[bool, bool, int | None, int | None]] = []

    def fake_resolve_epics(
        issues_dir: Path,
        project_key: str,
        configured_id: str | None,
        dry_run: bool,
        all_existing: set[str],
        include_dependency: bool,
        include_code: bool,
        dependency_priority: int | None,
        code_priority: int | None,
    ) -> dict[str, str]:
        epics_calls.append(
            (include_dependency, include_code, dependency_priority, code_priority)
        )
        return {"dependency": "kanbus-dep-epic", "code": "kanbus-code-epic"}

    monkeypatch.setattr(snyk_sync, "_resolve_snyk_epics", fake_resolve_epics)
    monkeypatch.setattr(snyk_sync, "_build_snyk_key_index", lambda *_args: {})
    monkeypatch.setattr(snyk_sync, "_build_file_task_index", lambda *_args: {})
    monkeypatch.setattr(
        snyk_sync,
        "_resolve_file_task",
        lambda issues_dir, project_key, target_file, category, ctx, file_task_index, all_existing: f"kanbus-task-{category}",
    )
    next_id = {"value": 0}

    def fake_generate_issue_identifier(request):
        next_id["value"] += 1
        return SimpleNamespace(
            identifier=f"{request.prefix}-new-{next_id['value']:03d}"
        )

    monkeypatch.setattr(
        snyk_sync, "generate_issue_identifier", fake_generate_issue_identifier
    )
    monkeypatch.setattr(
        snyk_sync,
        "_map_snyk_to_kanbus",
        lambda vuln, task_id, v1_data, target_file, root: build_issue(
            "__placeholder__",
            title=f"{target_file}:{vuln['attributes']['key']}",
            issue_type="sub-task",
            parent=task_id,
            labels=["security", "snyk"],
            custom={"snyk_key": vuln["attributes"]["key"]},
        ),
    )

    config = SnykConfiguration.model_validate(
        {"org_id": "org", "min_severity": "medium"}
    )
    result = snyk_sync.pull_from_snyk(tmp_path, config, "kanbus", dry_run=False)

    assert result.pulled == 2
    assert result.updated == 0
    assert result.skipped == 0
    assert epics_calls == [(True, True, 1, 2)]

    written_files = sorted(path.name for path in issues_dir.glob("*.json"))
    assert written_files == ["kanbus-new-001.json", "kanbus-new-002.json"]
    for file_name in written_files:
        written = read_issue_from_file(issues_dir / file_name)
        assert written.parent in {"kanbus-task-dependency", "kanbus-task-code"}
