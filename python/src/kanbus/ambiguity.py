"""Rendering and prompting helpers for ambiguous short identifiers."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Optional

from kanbus.ids import DEFAULT_SHORT_ID_LENGTH, ShortIdWidths, format_issue_key_with

if TYPE_CHECKING:  # pragma: no cover - circular import guard for typing only
    from kanbus.issue_lookup import AmbiguousCandidate


def _sorted_matches(matches: list["AmbiguousCandidate"]) -> list["AmbiguousCandidate"]:
    return sorted(matches, key=lambda issue: issue.identifier)


def _candidate_widths(matches: list["AmbiguousCandidate"]) -> ShortIdWidths:
    return ShortIdWidths.build(
        [issue.identifier for issue in matches], DEFAULT_SHORT_ID_LENGTH
    )


def render_ambiguous_error(candidate: str, matches: list["AmbiguousCandidate"]) -> str:
    """Render a human-readable ambiguity error listing formatted candidates."""
    widths = _candidate_widths(matches)
    lines = [f'ambiguous identifier "{candidate}"; {len(matches)} issues match:']
    for issue in _sorted_matches(matches):
        key = format_issue_key_with(issue.identifier, False, widths)
        lines.append(f"  {key}  [{issue.issue_type}, {issue.status}]  {issue.title}")
    lines.append("Re-run with one of the full IDs above.")
    return "\n".join(lines)


def ambiguous_matches_json(candidate: str, matches: list["AmbiguousCandidate"]) -> str:
    """Render the structured JSON ambiguity payload (full IDs included)."""
    widths = _candidate_widths(matches)
    payload = {
        "error": "ambiguous_identifier",
        "candidate": candidate,
        "matches": [
            {
                "id": issue.identifier,
                "key": format_issue_key_with(issue.identifier, False, widths),
                "type": issue.issue_type,
                "status": issue.status,
                "title": issue.title,
            }
            for issue in _sorted_matches(matches)
        ],
    }
    return json.dumps(payload, indent=2)


def prompt_ambiguous_choice(
    candidate: str, matches: list["AmbiguousCandidate"]
) -> Optional[str]:
    """Print the interactive disambiguation menu and read a selection."""
    widths = _candidate_widths(matches)
    ordered = _sorted_matches(matches)
    print(f'"{candidate}" is ambiguous; {len(matches)} issues match:\n')
    for index, issue in enumerate(ordered):
        key = format_issue_key_with(issue.identifier, False, widths)
        print(
            f"  {index + 1}) {key}  [{issue.issue_type}, {issue.status}]  {issue.title}"
        )
    print(f"\nSelect 1-{len(matches)}, or press Enter to cancel:")
    try:
        line = sys.stdin.readline()
    except Exception:
        return None
    try:
        choice = int(line.strip())
    except ValueError:
        return None
    if 1 <= choice <= len(ordered):
        return ordered[choice - 1].identifier
    return None
