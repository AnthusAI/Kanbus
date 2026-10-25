from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import issue_files
from test_helpers import build_issue


def test_service_request_raises_without_table_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(issue_files, "request_virtuus", lambda _root, _request: {})
    with pytest.raises(RuntimeError, match="no table handle"):
        issue_files._service_request(
            Path("/tmp/kanbus-root/project/issues"), {"action": "scan"}
        )


def test_service_request_injects_handle_and_returns_operation_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: list[object] = [{"handle": "handle-1"}, {"record": {"id": "kanbus-1"}}]
    captured: dict[str, object] = {}

    def fake_request_virtuus(root: Path, request: dict[str, object]) -> object:
        captured["root"] = root
        return responses.pop(0)

    monkeypatch.setattr(issue_files, "request_virtuus", fake_request_virtuus)
    result = issue_files._service_request(
        Path("/tmp/kanbus-root/project/issues"), {"action": "get", "pk": "kanbus-1"}
    )
    assert result == {"record": {"id": "kanbus-1"}}
    assert captured["root"] == Path("/tmp/kanbus-root")


def test_list_issue_identifiers_missing_directory_returns_empty(
    tmp_path: Path,
) -> None:
    assert issue_files.list_issue_identifiers(tmp_path / "missing") == set()


def test_read_issues_from_directory_missing_directory_returns_empty(
    tmp_path: Path,
) -> None:
    assert issue_files.read_issues_from_directory(tmp_path / "missing") == []


def test_ensure_no_skipped_issue_files_ignores_non_list_records(
    tmp_path: Path,
) -> None:
    issue_files._ensure_no_skipped_issue_files(tmp_path, "not-a-list")


def test_write_issue_to_file_rejects_directory(tmp_path: Path) -> None:
    target = tmp_path / "kanbus-1"
    target.mkdir()
    with pytest.raises(IsADirectoryError):
        issue_files.write_issue_to_file(build_issue("kanbus-1"), target)


def test_read_issue_from_file_does_not_load_the_issue_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    issues_directory = tmp_path / "issues"
    issues_directory.mkdir()
    for index in range(5):
        issue_files.write_issue_to_file(
            build_issue(f"kanbus-{index}"), issues_directory / f"kanbus-{index}.json"
        )

    def fail_on_table_load(_directory: Path) -> None:
        raise AssertionError("reading one issue must not load the whole directory")

    monkeypatch.setattr(issue_files, "_issue_table", fail_on_table_load)

    for index in range(5):
        loaded = issue_files.read_issue_from_file(
            issues_directory / f"kanbus-{index}.json"
        )
        assert loaded.identifier == f"kanbus-{index}"


def test_read_issue_from_file_reports_missing_and_unreadable_files(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError):
        issue_files.read_issue_from_file(tmp_path / "missing.json")

    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        issue_files.read_issue_from_file(tmp_path / "broken.json")

    (tmp_path / "list.json").write_text("[]", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        issue_files.read_issue_from_file(tmp_path / "list.json")
