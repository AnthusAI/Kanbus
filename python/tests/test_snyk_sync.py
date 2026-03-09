from __future__ import annotations

from pathlib import Path
import subprocess

from kanbus import snyk_sync


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


def test_detect_repo_from_git_returns_none_for_non_github_remote(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "ssh://gitlab.example.com/team/repo.git"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert snyk_sync._detect_repo_from_git(tmp_path) is None


class _FakeResponse:
    def __init__(self, ok: bool, status_code: int, payload: dict, text: str = "") -> None:
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
                        "attributes": {"name": "AnthusAI/Kanbus", "target_file": "repo-root"},
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
                    {
                        "attributes": {"key": "S-2", "effective_severity_level": "low"}
                    },
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


def test_fetch_all_snyk_issues_continues_when_non_package_type_fails(monkeypatch) -> None:
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
    def fake_post(
        url: str, headers: dict, json: dict, timeout: int
    ) -> _FakeResponse:
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


def test_map_snyk_to_kanbus_code_includes_location_custom_fields(tmp_path: Path) -> None:
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
