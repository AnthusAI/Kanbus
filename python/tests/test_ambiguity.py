"""Tests for ambiguous short-identifier helpers and CLI exit code 3."""

from __future__ import annotations

import json
from io import StringIO

import pytest

from kanbus import ambiguity, cli
from kanbus.issue_creation import IssueCreationError
from kanbus.issue_lookup import AmbiguousCandidate, IssueLookupError


def _candidates() -> list[AmbiguousCandidate]:
    return [
        AmbiguousCandidate(
            identifier="kanbus-aaaabbbb",
            title="Alpha",
            issue_type="task",
            status="open",
        ),
        AmbiguousCandidate(
            identifier="kanbus-aaaacccc",
            title="Bravo",
            issue_type="task",
            status="closed",
        ),
    ]


def test_render_ambiguous_error_lists_sorted_candidates() -> None:
    message = ambiguity.render_ambiguous_error("kanbus-aaaa", _candidates())
    assert 'ambiguous identifier "kanbus-aaaa"' in message
    assert "2 issues match" in message
    assert "Alpha" in message
    assert "Bravo" in message
    assert message.index("Alpha") < message.index("Bravo")
    assert message.endswith("Re-run with one of the full IDs above.")


def test_ambiguous_matches_json_payload() -> None:
    payload = json.loads(ambiguity.ambiguous_matches_json("kanbus-aaaa", _candidates()))
    assert payload["error"] == "ambiguous_identifier"
    assert payload["candidate"] == "kanbus-aaaa"
    assert [match["id"] for match in payload["matches"]] == [
        "kanbus-aaaabbbb",
        "kanbus-aaaacccc",
    ]
    assert payload["matches"][0]["title"] == "Alpha"


def test_prompt_ambiguous_choice_reads_selection(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("2\n"))
    chosen = ambiguity.prompt_ambiguous_choice("kanbus-aaaa", _candidates())
    assert chosen == "kanbus-aaaacccc"
    captured = capsys.readouterr()
    assert "ambiguous" in captured.out
    assert "1)" in captured.out
    assert "2)" in captured.out


def test_prompt_ambiguous_choice_rejects_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.stdin", StringIO("not-a-number\n"))
    assert ambiguity.prompt_ambiguous_choice("kanbus-aaaa", _candidates()) is None

    monkeypatch.setattr("sys.stdin", StringIO("9\n"))
    assert ambiguity.prompt_ambiguous_choice("kanbus-aaaa", _candidates()) is None

    monkeypatch.setattr("sys.stdin", StringIO("\n"))
    assert ambiguity.prompt_ambiguous_choice("kanbus-aaaa", _candidates()) is None


def test_prompt_ambiguous_choice_handles_read_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenStdin:
        def readline(self) -> str:
            raise OSError("stdin unavailable")

    monkeypatch.setattr("sys.stdin", BrokenStdin())
    assert ambiguity.prompt_ambiguous_choice("kanbus-aaaa", _candidates()) is None


def test_raise_wrapped_domain_error_maps_ambiguous_lookup_to_exit_code_exception() -> None:
    lookup_error = IssueLookupError(
        ambiguity.render_ambiguous_error("kanbus-aaaa", _candidates()),
        candidate="kanbus-aaaa",
        matches=_candidates(),
    )
    try:
        raise lookup_error
    except IssueLookupError as error:
        wrapped = IssueCreationError(str(error))
        wrapped.__cause__ = error

    with pytest.raises(cli.AmbiguousIdentifierException) as raised:
        cli._raise_wrapped_domain_error(wrapped)
    assert raised.value.exit_code == 3


def test_raise_wrapped_domain_error_falls_back_to_click_exception() -> None:
    wrapped = IssueCreationError("unknown issue type")
    with pytest.raises(cli.click.ClickException, match="unknown issue type"):
        cli._raise_wrapped_domain_error(wrapped)
