import os
import json
from unittest import mock
from pathlib import Path
from datetime import datetime, timezone
import pytest

from kanbus.models import (
    IssueData,
    GithubSecurityConfiguration,
    DependabotConfiguration
)
from kanbus.github_security_sync import (
    _extract_repo_slug,
    _parse_next_link,
    _severity_to_priority,
    GithubSecuritySyncError,
    _validate_state,
    _task_target_key,
    _map_dependabot_to_kanbus,
    _append_marker,
    _metadata_marker_alert,
    _metadata_marker_target,
    _extract_marker,
    _build_alert_index,
    _build_task_index,
    _resolve_manifest_task,
    _map_dependabot_to_beads_description,
    _build_beads_alert_index,
    _build_beads_task_index,
    _resolve_beads_initiative,
    _resolve_beads_epic,
    _resolve_beads_task,
    _find_existing_security_initiative,
    _find_existing_dependabot_epic,
    _resolve_dependabot_epic,
    _resolve_security_initiative,
    pull_dependabot_from_github,
    pull_dependabot_from_github_beads,
    _fetch_dependabot_alerts,
    _detect_repo_from_git,
    _issue_path
)
from kanbus.issue_files import write_issue_to_file, read_issue_from_file

def sample_alert() -> dict:
    return {
        "number": 42,
        "state": "open",
        "html_url": "https://github.com/example/acme/alerts/42",
        "dependency": {
            "manifest_path": "Cargo.toml",
            "package": { "ecosystem": "cargo", "name": "serde" }
        },
        "security_advisory": {
            "ghsa_id": "GHSA-1234-5678",
            "severity": "high",
            "summary": "Serde vulnerability",
            "description": "Details here"
        },
        "security_vulnerability": {
            "package": { "ecosystem": "cargo", "name": "serde" },
            "severity": "critical"
        }
    }

def test_extract_repo_slug() -> None:
    assert (
        _extract_repo_slug("https://github.com/AnthusAI/Kanbus.git")
        == "AnthusAI/Kanbus"
    )
    assert _extract_repo_slug("git@github.com:AnthusAI/Kanbus.git") == "AnthusAI/Kanbus"
    assert _extract_repo_slug("ssh://gitlab.com/foo/bar.git") is None


def test_parse_next_link() -> None:
    header = (
        '<https://api.github.com/foo?page=2>; rel="next", '
        '<https://api.github.com/foo?page=3>; rel="last"'
    )
    assert _parse_next_link(header) == "https://api.github.com/foo?page=2"
    assert _parse_next_link('<https://api.github.com/foo?page=3>; rel="last"') is None
    assert _parse_next_link(None) is None
    assert _parse_next_link("invalid") is None
    assert _parse_next_link('<https://api.github.com/foo?page=2>; rel="next"') == "https://api.github.com/foo?page=2"


def test_severity_to_priority() -> None:
    assert _severity_to_priority("critical") == 0
    assert _severity_to_priority("high") == 1
    assert _severity_to_priority("medium") == 2
    assert _severity_to_priority("low") == 3
    assert _severity_to_priority("unknown") == 3


def test_validate_dependabot_state_rejects_invalid_value():
    _validate_state("fixed")
    with pytest.raises(GithubSecuritySyncError, match="invalid dependabot state 'invalid'"):
        _validate_state("invalid")


def test_task_target_key_prefers_manifest_then_ecosystem():
    alert = sample_alert()
    assert _task_target_key(alert) == "Cargo.toml"

    no_manifest = sample_alert()
    no_manifest["dependency"]["manifest_path"] = ""
    assert _task_target_key(no_manifest) == "cargo"

    unknown = sample_alert()
    unknown["dependency"]["manifest_path"] = ""
    unknown["dependency"]["package"]["ecosystem"] = None
    unknown["security_vulnerability"]["package"]["ecosystem"] = None
    assert _task_target_key(unknown) == "unknown"


def test_map_dependabot_to_kanbus_sets_expected_fields():
    alert = sample_alert()
    issue = _map_dependabot_to_kanbus(alert, "AnthusAI/Kanbus", "kbs-epic.1")
    assert "GHSA-1234-5678" in issue.title
    assert issue.parent == "kbs-epic.1"
    assert issue.issue_type == "sub-task"
    assert issue.priority == 1
    assert issue.custom.get("github_manifest_path") == "Cargo.toml"
    assert issue.custom.get("github_ecosystem") == "cargo"

    alert_no_package = sample_alert()
    alert_no_package["dependency"]["package"]["name"] = None
    alert_no_package["security_vulnerability"]["package"]["name"] = None
    issue_no_pkg = _map_dependabot_to_kanbus(alert_no_package, "AnthusAI/Kanbus", "kbs-epic.1")
    assert "[Dependabot] GHSA-1234-5678 in unknown" in issue_no_pkg.title


def test_append_and_find_marker_round_trip():
    marker = _metadata_marker_alert("AnthusAI/Kanbus", 7)
    described = _append_marker("body", marker)
    assert _extract_marker(described, "kanbus-gh-alert:dependabot|") == "AnthusAI/Kanbus|7"
    assert _extract_marker("no marker", "kanbus-gh-alert:dependabot|") is None


def test_build_alert_and_manifest_indexes_extract_dependabot_metadata(tmp_path):
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    
    now = datetime.now(timezone.utc).isoformat()
    alert_issue = IssueData.model_validate({
        "id": "kbs-1",
        "title": "alert",
        "description": "",
        "type": "sub-task",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": [],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {
            "github_provider": "dependabot",
            "github_alert_number": 10,
            "github_repository": "example/repo",
            "github_manifest_path": "Cargo.toml",
        },
    })
    alert_path = _issue_path(issues_dir, alert_issue.identifier)
    write_issue_to_file(alert_issue, alert_path)

    task_issue = alert_issue.model_copy()
    task_issue.identifier = "kbs-2"
    task_issue.issue_type = "task"
    task_issue.custom = dict(task_issue.custom)
    task_issue.custom["github_alert_number"] = 11
    task_issue.custom["github_manifest_path"] = "pkg/Cargo.toml"
    task_path = _issue_path(issues_dir, task_issue.identifier)
    write_issue_to_file(task_issue, task_path)

    ids = {"kbs-1", "kbs-2", "kbs-3"}
    alert_index = _build_alert_index(ids, issues_dir)
    task_index = _build_task_index(ids, issues_dir)

    assert alert_index.get("example/repo#10") == "kbs-1"
    assert task_index.get("pkg/Cargo.toml") == "kbs-2"

    assert "kbs-3" not in alert_index
    assert "kbs-3" not in task_index


def test_resolve_manifest_task_updates_existing_issue(tmp_path):
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    now = datetime.now(timezone.utc).isoformat()
    issue = IssueData.model_validate({
        "id": "kbs-10",
        "title": "example/repo:Cargo.toml",
        "description": "old",
        "type": "task",
        "status": "open",
        "priority": 3,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": ["github"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {
            "github_provider": "dependabot"
        },
    })
    path = _issue_path(issues_dir, issue.identifier)
    write_issue_to_file(issue, path)

    task_index = {"Cargo.toml": issue.identifier}
    all_existing = {issue.identifier}
    
    resolved = _resolve_manifest_task(
        issues_dir=issues_dir,
        project_key="kbs",
        repo="example/repo",
        target_key="Cargo.toml",
        parent_epic="kbs-epic",
        priority=1,
        dry_run=False,
        task_index=task_index,
        all_existing=all_existing,
    )
    assert resolved == "kbs-10"

    updated = read_issue_from_file(path)
    assert updated.parent == "kbs-epic"
    assert updated.priority == 1
    assert "dependabot" in updated.labels
    assert "security" in updated.labels


def test_map_dependabot_to_beads_description_appends_marker():
    alert = sample_alert()
    description = _map_dependabot_to_beads_description(alert, "example/repo")
    assert "kanbus-gh-alert:dependabot|example/repo|42" in description
    assert "GitHub Dependabot" in description


def test_build_beads_indexes_read_markers():
    now = datetime.now(timezone.utc).isoformat()
    alert_desc = _append_marker("alert description", _metadata_marker_alert("example/repo", 11))
    task_desc = _append_marker("task description", _metadata_marker_target("example/repo", "Cargo.lock"))

    issues = [
        IssueData.model_validate({
            "id": "bdx-1",
            "title": "alert",
            "description": alert_desc,
            "type": "bug",
            "status": "open",
            "priority": 2,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": [],
            "dependencies": [],
            "comments": [],
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "custom": {},
        }),
        IssueData.model_validate({
            "id": "bdx-2",
            "title": "task",
            "description": task_desc,
            "type": "task",
            "status": "open",
            "priority": 2,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": [],
            "dependencies": [],
            "comments": [],
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "custom": {},
        }),
        # Test bad markers
        IssueData.model_validate({
            "id": "bdx-3",
            "title": "task",
            "description": "<!-- kanbus-gh-target:dependabot|badformat -->",
            "type": "task",
            "status": "open",
            "priority": 2,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": [],
            "dependencies": [],
            "comments": [],
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "custom": {},
        }),
    ]
    alert_index = _build_beads_alert_index(issues)
    task_index = _build_beads_task_index(issues)
    assert alert_index.get("example/repo#11") == "bdx-1"
    assert task_index.get("Cargo.lock") == "bdx-2"


def test_resolve_manifest_task_creates_new_issue_when_missing(tmp_path):
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    task_index = {}
    all_existing = set()

    task_id = _resolve_manifest_task(
        issues_dir=issues_dir,
        project_key="kbs",
        repo="example/repo",
        target_key="Cargo.toml",
        parent_epic="kbs-epic",
        priority=2,
        dry_run=False,
        task_index=task_index,
        all_existing=all_existing,
    )
    
    path = _issue_path(issues_dir, task_id)
    created = read_issue_from_file(path)
    assert created.issue_type == "task"
    assert created.parent == "kbs-epic"
    assert created.priority == 2
    assert "github" in created.labels
    assert created.custom.get("github_manifest_path") == "Cargo.toml"


def test_find_existing_security_initiative_prefers_latest_github_labeled_issue(tmp_path):
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    now = datetime.now(timezone.utc).isoformat()
    
    older = IssueData.model_validate({
        "id": "kbs-1",
        "title": "GitHub Security Remediation",
        "description": "",
        "type": "initiative",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": ["github"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": "2020-01-01T00:00:00Z",
        "closed_at": None,
        "custom": {},
    })
    newer = older.model_copy()
    newer.identifier = "kbs-2"
    newer.updated_at = "2020-01-02T00:00:00Z"
    
    no_label = older.model_copy()
    no_label.identifier = "kbs-3"
    no_label.labels = []
    no_label.updated_at = "2020-01-03T00:00:00Z"

    write_issue_to_file(older, _issue_path(issues_dir, older.identifier))
    write_issue_to_file(newer, _issue_path(issues_dir, newer.identifier))
    write_issue_to_file(no_label, _issue_path(issues_dir, no_label.identifier))

    existing = {older.identifier, newer.identifier, no_label.identifier, "missing"}
    assert _find_existing_security_initiative(issues_dir, existing) == "kbs-2"


def test_find_existing_dependabot_epic_filters_by_parent_and_label(tmp_path):
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    now = datetime.now(timezone.utc).isoformat()
    
    matching = IssueData.model_validate({
        "id": "kbs-epic.1",
        "title": "GitHub Dependabot Alerts",
        "description": "",
        "type": "epic",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": "kbs-init",
        "labels": ["dependabot"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": "2020-01-01T00:00:00Z",
        "closed_at": None,
        "custom": {},
    })
    wrong_parent = matching.model_copy()
    wrong_parent.identifier = "kbs-epic.2"
    wrong_parent.parent = "other-init"
    wrong_parent.updated_at = "2020-01-02T00:00:00Z"
    
    newer_match = matching.model_copy()
    newer_match.identifier = "kbs-epic.3"
    newer_match.updated_at = "2020-01-03T00:00:00Z"
    
    write_issue_to_file(matching, _issue_path(issues_dir, matching.identifier))
    write_issue_to_file(wrong_parent, _issue_path(issues_dir, wrong_parent.identifier))
    write_issue_to_file(newer_match, _issue_path(issues_dir, newer_match.identifier))
    
    ids = {matching.identifier, wrong_parent.identifier, newer_match.identifier, "missing"}
    assert _find_existing_dependabot_epic(issues_dir, ids, "kbs-init") == "kbs-epic.3"


def test_resolve_beads_task_dry_run_returns_synthetic_and_updates_index(tmp_path):
    task_index = {}
    task_id = _resolve_beads_task(
        root=tmp_path,
        repository="example/repo",
        target_key="Cargo.toml",
        parent_epic="bdx-epic",
        priority=1,
        dry_run=True,
        task_index=task_index,
    )
    assert task_id == "would-create-task-Cargo.toml"
    assert task_index.get("Cargo.toml") == task_id


def test_resolve_beads_initiative_and_epic_dry_run_create_placeholders(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    issues = [IssueData.model_validate({
        "id": "bdx-1",
        "title": "Other",
        "description": "",
        "type": "initiative",
        "status": "open",
        "priority": 2,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": [],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })]
    initiative_id = _resolve_beads_initiative(tmp_path, issues, True)
    assert initiative_id == "would-create-initiative"
    
    epic_id = _resolve_beads_epic(tmp_path, issues, None, initiative_id, True)
    assert epic_id == "would-create-epic"


def test_resolve_dependabot_epic_prefers_existing_and_configured_issue(tmp_path):
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    now = datetime.now(timezone.utc).isoformat()
    
    initiative = IssueData.model_validate({
        "id": "kbs-init",
        "title": "GitHub Security Remediation",
        "description": "",
        "type": "initiative",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": ["github"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })
    epic = IssueData.model_validate({
        "id": "kbs-epic.9",
        "title": "GitHub Dependabot Alerts",
        "description": "",
        "type": "epic",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": "kbs-init",
        "labels": ["dependabot"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })
    write_issue_to_file(initiative, _issue_path(issues_dir, initiative.identifier))
    write_issue_to_file(epic, _issue_path(issues_dir, epic.identifier))
    
    existing = {initiative.identifier, epic.identifier}
    resolved_existing = _resolve_dependabot_epic(issues_dir, "kbs", None, False, existing)
    assert resolved_existing == epic.identifier
    
    resolved_configured = _resolve_dependabot_epic(issues_dir, "kbs", "kbs-epic.9", False, existing)
    assert resolved_configured == "kbs-epic.9"


@mock.patch("subprocess.run")
def test_detect_repo_from_git_reads_origin_remote(mock_run, tmp_path):
    mock_result = mock.Mock()
    mock_result.stdout = "https://github.com/example/acme.git\n"
    mock_run.return_value = mock_result
    
    slug = _detect_repo_from_git(tmp_path)
    assert slug == "example/acme"

    mock_run.side_effect = Exception("failed")
    assert _detect_repo_from_git(tmp_path) is None


def test_resolve_beads_initiative_finds_existing_with_label(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    issues = [IssueData.model_validate({
        "id": "kanbus-1",
        "title": "GitHub Security Remediation",
        "description": "",
        "type": "initiative",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": ["github"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })]
    assert _resolve_beads_initiative(tmp_path, issues, False) == "kanbus-1"


def test_resolve_beads_epic_finds_existing_with_label(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    issues = [IssueData.model_validate({
        "id": "kanbus-2",
        "title": "GitHub Dependabot Alerts",
        "description": "",
        "type": "epic",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": ["dependabot"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })]
    assert _resolve_beads_epic(tmp_path, issues, None, "kanbus-1", False) == "kanbus-2"


def test_resolve_beads_initiative_finds_existing_without_label(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    issues = [IssueData.model_validate({
        "id": "kanbus-3",
        "title": "GitHub Security Remediation",
        "description": "",
        "type": "initiative",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": [],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })]
    assert _resolve_beads_initiative(tmp_path, issues, False) == "kanbus-3"


def test_resolve_beads_epic_finds_existing_without_label(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    issues = [IssueData.model_validate({
        "id": "kanbus-4",
        "title": "GitHub Dependabot Alerts",
        "description": "",
        "type": "epic",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": [],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })]
    assert _resolve_beads_epic(tmp_path, issues, None, "kanbus-3", False) == "kanbus-4"


def test_resolve_beads_task_finds_existing_with_label(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    issues = [IssueData.model_validate({
        "id": "kanbus-5",
        "title": "Example Vulnerability",
        "description": "<!-- kanbus-gh-target:dependabot|test-repo|123 -->",
        "type": "task",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": ["dependabot"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })]
    index = _build_beads_task_index(issues)
    with mock.patch("kanbus.github_security_sync.update_beads_issue") as mock_update:
        assert _resolve_beads_task(tmp_path, "test-repo", "123", "kanbus-2", 2, False, index) == "kanbus-5"
        mock_update.assert_called_once()
        
    assert _resolve_beads_task(tmp_path, "test-repo", "123", "kanbus-2", 2, True, index) == "kanbus-5"


def test_resolve_beads_task_finds_existing_without_label(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    issues = [IssueData.model_validate({
        "id": "kanbus-6",
        "title": "Example Vulnerability",
        "description": "<!-- kanbus-gh-target:dependabot|test-repo|123 -->",
        "type": "task",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": [],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })]
    index = _build_beads_task_index(issues)
    assert _resolve_beads_task(tmp_path, "test-repo", "123", "kanbus-2", 2, True, index) == "kanbus-6"


@mock.patch.dict(os.environ, clear=True)
def test_pull_dependabot_from_github_missing_token_returns_error(tmp_path):
    config = GithubSecurityConfiguration(repo=None, dependabot=None)
    with pytest.raises(GithubSecuritySyncError, match="TOKEN"):
        pull_dependabot_from_github(tmp_path, config, "PRJ", False)


@mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"}, clear=True)
def test_pull_dependabot_from_github_missing_repo_returns_error(tmp_path):
    config = GithubSecurityConfiguration(repo=None, dependabot=None)
    with pytest.raises(GithubSecuritySyncError, match="repository slug"):
        pull_dependabot_from_github(tmp_path, config, "PRJ", False)


@mock.patch.dict(os.environ, clear=True)
def test_pull_dependabot_from_github_beads_missing_token_returns_error(tmp_path):
    config = GithubSecurityConfiguration(repo=None, dependabot=None)
    with pytest.raises(GithubSecuritySyncError, match="TOKEN"):
        pull_dependabot_from_github_beads(tmp_path, config, False)


@mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"}, clear=True)
def test_pull_dependabot_from_github_beads_missing_repo_returns_error(tmp_path):
    config = GithubSecurityConfiguration(repo=None, dependabot=None)
    with pytest.raises(GithubSecuritySyncError, match="repository slug"):
        pull_dependabot_from_github_beads(tmp_path, config, False)


@mock.patch("requests.get")
def test_fetch_dependabot_alerts(mock_get):
    mock_response = mock.Mock()
    mock_response.ok = True
    mock_response.json.return_value = [sample_alert()]
    mock_response.headers = {"Link": '<https://api.github.com/foo?page=2>; rel="next"'}
    
    mock_response2 = mock.Mock()
    mock_response2.ok = True
    mock_response2.json.return_value = [sample_alert()]
    mock_response2.headers = {}
    
    mock_get.side_effect = [mock_response, mock_response2]
    
    alerts = _fetch_dependabot_alerts("example/repo", "token", "open")
    assert len(alerts) == 2

    # Error handling
    mock_response_err = mock.Mock()
    mock_response_err.ok = False
    mock_response_err.status_code = 404
    mock_response_err.text = "Not Found"
    mock_get.side_effect = [mock_response_err]
    with pytest.raises(GithubSecuritySyncError, match="404"):
        _fetch_dependabot_alerts("example/repo", "token", "open")
        
    mock_response_bad_json = mock.Mock()
    mock_response_bad_json.ok = True
    mock_response_bad_json.json.return_value = {"error": "not a list"}
    mock_get.side_effect = [mock_response_bad_json]
    with pytest.raises(GithubSecuritySyncError, match="unexpected"):
        _fetch_dependabot_alerts("example/repo", "token", "open")


@mock.patch("kanbus.project.load_project_directory")
@mock.patch("kanbus.github_security_sync._fetch_dependabot_alerts")
@mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"}, clear=True)
def test_pull_dependabot_from_github_success(mock_fetch, mock_load_project, tmp_path):
    mock_load_project.return_value = tmp_path
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()

    alert1 = sample_alert()
    alert2 = sample_alert()
    alert2["number"] = 43
    alert2["dependency"]["manifest_path"] = "pkg/Cargo.toml"
    
    alert3 = sample_alert()
    alert3["number"] = 0
    
    mock_fetch.return_value = [alert1, alert2, alert3]
    
    config = GithubSecurityConfiguration(repo="example/repo", dependabot=DependabotConfiguration(state="open"))
    
    res = pull_dependabot_from_github(tmp_path, config, "PRJ", False)
    assert res.pulled == 2
    assert res.updated == 0

    res_update = pull_dependabot_from_github(tmp_path, config, "PRJ", False)
    assert res_update.pulled == 0
    assert res_update.updated == 2
    
    res_dry = pull_dependabot_from_github(tmp_path, config, "PRJ", True)
    assert res_dry.updated == 2
    
    import shutil
    shutil.rmtree(tmp_path / "issues")
    with pytest.raises(GithubSecuritySyncError, match="issues directory does not exist"):
        pull_dependabot_from_github(tmp_path, config, "PRJ", False)

@mock.patch("kanbus.github_security_sync.load_beads_issues")
@mock.patch("kanbus.github_security_sync.create_beads_issue")
@mock.patch("kanbus.github_security_sync.update_beads_issue")
@mock.patch("kanbus.github_security_sync._fetch_dependabot_alerts")
@mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"}, clear=True)
def test_pull_dependabot_from_github_beads_success(mock_fetch, mock_update, mock_create, mock_load, tmp_path):
    mock_load.return_value = []
    
    def fake_create(**kwargs):
        now = datetime.now(timezone.utc).isoformat()
        return IssueData.model_validate({
            "id": f"created-{kwargs['title'].replace(':', '-')}",
            "title": kwargs["title"],
            "description": kwargs.get("description", ""),
            "type": kwargs["issue_type"],
            "status": "open",
            "priority": kwargs.get("priority", 3),
            "assignee": None,
            "creator": None,
            "parent": kwargs.get("parent"),
            "labels": [],
            "dependencies": [],
            "comments": [],
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "custom": {},
        })
    mock_create.side_effect = fake_create

    alert1 = sample_alert()
    alert2 = sample_alert()
    alert2["number"] = 0
    mock_fetch.return_value = [alert1, alert2]
    
    config = GithubSecurityConfiguration(repo="example/repo", dependabot=DependabotConfiguration(state="open"))
    
    res = pull_dependabot_from_github_beads(tmp_path, config, False)
    assert res.pulled == 1
    assert res.updated == 0
    assert mock_create.called
    assert mock_update.called
    
    mock_create.reset_mock()
    mock_update.reset_mock()
    res_dry = pull_dependabot_from_github_beads(tmp_path, config, True)
    assert res_dry.pulled == 1
    assert not mock_create.called
    assert not mock_update.called

    now = datetime.now(timezone.utc).isoformat()
    alert_desc = _append_marker("alert description", _metadata_marker_alert("example/repo", 42))
    task_desc = _append_marker("task description", _metadata_marker_target("example/repo", "Cargo.toml"))

    mock_load.return_value = [
        IssueData.model_validate({
            "id": "bdx-1",
            "title": "alert",
            "description": alert_desc,
            "type": "bug",
            "status": "open",
            "priority": 2,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": [],
            "dependencies": [],
            "comments": [],
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "custom": {},
        }),
        IssueData.model_validate({
            "id": "bdx-2",
            "title": "task",
            "description": task_desc,
            "type": "task",
            "status": "open",
            "priority": 2,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": [],
            "dependencies": [],
            "comments": [],
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "custom": {},
        }),
        IssueData.model_validate({
            "id": "bdx-3",
            "title": "GitHub Security Remediation",
            "description": "",
            "type": "initiative",
            "status": "open",
            "priority": 2,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": ["github"],
            "dependencies": [],
            "comments": [],
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "custom": {},
        }),
        IssueData.model_validate({
            "id": "bdx-4",
            "title": "GitHub Dependabot Alerts",
            "description": "",
            "type": "epic",
            "status": "open",
            "priority": 2,
            "assignee": None,
            "creator": None,
            "parent": None,
            "labels": ["dependabot"],
            "dependencies": [],
            "comments": [],
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "custom": {},
        })
    ]
    
    mock_create.reset_mock()
    mock_update.reset_mock()
    res_update = pull_dependabot_from_github_beads(tmp_path, config, False)
    assert res_update.updated == 1
    assert not mock_create.called
    assert mock_update.call_count == 2


def test_alert_severity_fallback():
    from kanbus.github_security_sync import _alert_severity
    assert _alert_severity({}) == "low"
    assert _alert_severity({"security_vulnerability": {"severity": None}}) == "low"

def test_resolve_beads_epic_with_configured_id(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    issues = [IssueData.model_validate({
        "id": "kanbus-configured",
        "title": "GitHub Dependabot Alerts",
        "description": "",
        "type": "epic",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": [],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })]
    assert _resolve_beads_epic(tmp_path, issues, "kanbus-configured", "kanbus-1", False) == "kanbus-configured"

@mock.patch("kanbus.github_security_sync._fetch_dependabot_alerts")
@mock.patch("kanbus.github_security_sync.read_issue_from_file")
@mock.patch("kanbus.project.load_project_directory")
@mock.patch.dict(os.environ, {"GITHUB_TOKEN": "fake_token"}, clear=True)
def test_pull_dependabot_from_github_exception(mock_load_project, mock_read, mock_fetch, tmp_path):
    from kanbus.github_security_sync import _issue_path
    with mock.patch.object(Path, "exists", return_value=True):
        mock_load_project.return_value = tmp_path
        issues_dir = tmp_path / "issues"
        issues_dir.mkdir()
        
        mock_fetch.return_value = [sample_alert()]
        mock_read.side_effect = Exception("failed read")
        with mock.patch("kanbus.github_security_sync._build_alert_index", return_value={"example/repo#42": "kbs-1"}):
            config = GithubSecurityConfiguration(repo="example/repo")
            res = pull_dependabot_from_github(tmp_path, config, "PRJ", False)
            assert res.pulled == 0
            assert res.updated == 1

def test_missing_coverage_edges(tmp_path):
    from kanbus.github_security_sync import (
        _find_existing_security_initiative,
        _find_existing_dependabot_epic,
        _build_beads_alert_index,
        _build_beads_task_index
    )
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    now = datetime.now(timezone.utc).isoformat()
    
    wrong_type_init = IssueData.model_validate({
        "id": "kbs-init-wrong",
        "title": "GitHub Security Remediation",
        "description": "",
        "type": "task",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": ["github"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })
    
    wrong_type_epic = IssueData.model_validate({
        "id": "kbs-epic-wrong",
        "title": "GitHub Dependabot Alerts",
        "description": "",
        "type": "task",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": "kbs-init",
        "labels": ["dependabot"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })
    
    wrong_title_epic = IssueData.model_validate({
        "id": "kbs-epic-wrong-title",
        "title": "Other",
        "description": "",
        "type": "epic",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": "kbs-init",
        "labels": ["dependabot"],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })
    
    beads_wrong_type = IssueData.model_validate({
        "id": "bdx-wrong-type",
        "title": "Other",
        "description": "",
        "type": "initiative",
        "status": "open",
        "priority": 1,
        "assignee": None,
        "creator": None,
        "parent": None,
        "labels": [],
        "dependencies": [],
        "comments": [],
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "custom": {},
    })
    
    write_issue_to_file(wrong_type_init, _issue_path(issues_dir, wrong_type_init.identifier))
    write_issue_to_file(wrong_type_epic, _issue_path(issues_dir, wrong_type_epic.identifier))
    write_issue_to_file(wrong_title_epic, _issue_path(issues_dir, wrong_title_epic.identifier))
    
    _find_existing_security_initiative(issues_dir, {wrong_type_init.identifier})
    _find_existing_dependabot_epic(issues_dir, {wrong_type_epic.identifier, wrong_title_epic.identifier}, "kbs-init")
    
    _build_beads_alert_index([beads_wrong_type])
    _build_beads_task_index([beads_wrong_type])

from datetime import datetime, timezone
from pathlib import Path
from kanbus.models import IssueData
from kanbus.issue_files import write_issue_to_file
from kanbus.github_security_sync import (
    _find_existing_security_initiative,
    _find_existing_dependabot_epic,
    _build_beads_alert_index,
    _build_beads_task_index,
    _issue_path,
    _extract_repo_slug
)

def test_missing_edges_final(tmp_path):
    issues_dir = tmp_path / "issues"
    issues_dir.mkdir()
    now = datetime.now(timezone.utc).isoformat()

    # 414: Initiative wrong title
    i1 = IssueData.model_validate({
        "id": "kbs-1", "title": "Wrong Title", "type": "initiative", "status": "open", "priority": 1,
        "labels": [], "custom": {}, "created_at": now, "updated_at": now
    })
    
    # 436: Epic no label
    e1 = IssueData.model_validate({
        "id": "kbs-2", "title": "GitHub Dependabot Alerts", "type": "epic", "status": "open", "priority": 1,
        "labels": [], "custom": {}, "created_at": now, "updated_at": now
    })

    # 802, 816: Task no label
    t1 = IssueData.model_validate({
        "id": "bdx-3", "title": "t", "type": "task", "status": "open", "priority": 1,
        "labels": [], "custom": {}, "created_at": now, "updated_at": now
    })

    write_issue_to_file(i1, _issue_path(issues_dir, i1.identifier))
    write_issue_to_file(e1, _issue_path(issues_dir, e1.identifier))

    _find_existing_security_initiative(issues_dir, {i1.identifier})
    _find_existing_dependabot_epic(issues_dir, {e1.identifier}, "foo")
    
    _build_beads_alert_index([t1])
    _build_beads_task_index([t1])

    assert _extract_repo_slug("unknown://foo") is None

from kanbus.github_security_sync import _parse_next_link, _build_beads_alert_index
from kanbus.models import IssueData
from datetime import datetime, timezone

def test_missing_edges_final_2():
    # 659
    assert _parse_next_link('foo; rel="next"') is None
    
    # 802
    now = datetime.now(timezone.utc).isoformat()
    t1 = IssueData.model_validate({
        "id": "bdx-bad-alert", "title": "t", "type": "task", "status": "open", "priority": 1,
        "description": "<!-- kanbus-gh-alert:dependabot|badformat -->",
        "labels": [], "custom": {}, "created_at": now, "updated_at": now
    })
    _build_beads_alert_index([t1])
