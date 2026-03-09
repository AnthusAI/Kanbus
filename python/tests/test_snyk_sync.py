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
