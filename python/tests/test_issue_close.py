from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import issue_close

from test_helpers import build_issue


def test_close_issue_delegates_to_update_with_closed_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    expected = build_issue("kanbus-1", status="closed")

    def fake_update_issue(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(issue_close, "update_issue", fake_update_issue)

    result = issue_close.close_issue(tmp_path, "kanbus-1")

    assert result.identifier == "kanbus-1"
    assert result.status == "closed"
    assert captured["root"] == tmp_path
    assert captured["identifier"] == "kanbus-1"
    assert captured["status"] == "closed"
    assert captured["validate"] is True
    assert captured["claim"] is False


def test_close_issue_wraps_update_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        issue_close,
        "update_issue",
        lambda **_kwargs: (_ for _ in ()).throw(
            issue_close.IssueUpdateError("update failed")
        ),
    )

    with pytest.raises(issue_close.IssueCloseError, match="update failed"):
        issue_close.close_issue(tmp_path, "kanbus-2")
