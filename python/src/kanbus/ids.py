"""
Issue identifier generation and short-ID display formatting.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Iterable, Optional, Set

from pydantic import BaseModel, Field

DEFAULT_SHORT_ID_LENGTH = 4
MAX_SHORT_ID_LENGTH = 32


class IssueIdentifierRequest(BaseModel):
    """
    Request to generate a unique issue identifier.

    :param title: The issue title for uniqueness checks.
    :type title: str
    :param existing_ids: Set of existing IDs to avoid collisions.
    :type existing_ids: Set[str]
    :param prefix: ID prefix from configuration.
    :type prefix: str
    """

    title: str = Field(min_length=1)
    existing_ids: Set[str] = Field(default_factory=set)
    prefix: str = Field(default="kanbus", min_length=1)
    requested_id: Optional[str] = None


@dataclass(frozen=True)
class IssueIdentifierResult:
    """Result of issue identifier generation."""

    identifier: str


_TEST_UUID_SEQUENCE: Optional[list[str]] = None


def set_test_uuid_sequence(sequence: Optional[Iterable[str]]) -> None:
    """
    Override UUID generation for deterministic tests.

    :param sequence: Sequence of UUID strings to use, or None to clear.
    :type sequence: Optional[Iterable[str]]
    """
    global _TEST_UUID_SEQUENCE
    _TEST_UUID_SEQUENCE = list(sequence) if sequence is not None else None


def _next_uuid_value() -> str:
    if _TEST_UUID_SEQUENCE:
        return _TEST_UUID_SEQUENCE.pop(0)
    return str(uuid.uuid4())


def _split_identifier(identifier: str) -> tuple[Optional[str], str, Optional[str]]:
    """Split an identifier into (project key, normalized hash base, dotted tail)."""
    if identifier.isdigit():
        return None, identifier, None
    key: Optional[str] = None
    remainder = identifier
    if "-" in identifier:
        parts = identifier.split("-", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            key, remainder = parts
    base = remainder
    tail: Optional[str] = None
    if "." in remainder:
        head, tail_candidate = remainder.split(".", 1)
        if head:
            base, tail = head, tail_candidate
    elif remainder.endswith("."):
        base = remainder[:-1]
    return key, base, tail


def _normalized_base(identifier: str) -> str:
    _, base, _ = _split_identifier(identifier)
    return base.replace("-", "")


def _longest_common_prefix_length(left: str, right: str) -> int:
    total = 0
    for left_ch, right_ch in zip(left, right):
        if left_ch != right_ch:
            break
        total += 1
    return total


def _clamp_short_id_length(length: int) -> int:
    return max(1, min(length, MAX_SHORT_ID_LENGTH))


@dataclass
class ShortIdWidths:
    """Display widths for short IDs derived from a universe of full identifiers."""

    default_len: int = DEFAULT_SHORT_ID_LENGTH
    widths: dict[str, int] = field(default_factory=dict)

    @classmethod
    def build(cls, universe: Iterable[str], default_len: int) -> "ShortIdWidths":
        """Build widths from full identifiers, widening only colliding groups."""
        default_len = _clamp_short_id_length(default_len)
        groups: dict[str, list[tuple[str, str]]] = {}
        for identifier in universe:
            if identifier.isdigit():
                continue
            key, _, _ = _split_identifier(identifier)
            normalized = _normalized_base(identifier)
            if not normalized:
                continue
            groups.setdefault(key or "", []).append((identifier, normalized))
        widths: dict[str, int] = {}
        for entries in groups.values():
            entries.sort(key=lambda entry: entry[1])
            for index, (identifier, normalized) in enumerate(entries):
                width = default_len
                if index > 0:
                    width = max(
                        width,
                        _longest_common_prefix_length(normalized, entries[index - 1][1]) + 1,
                    )
                if index + 1 < len(entries):
                    width = max(
                        width,
                        _longest_common_prefix_length(normalized, entries[index + 1][1]) + 1,
                    )
                width = min(_clamp_short_id_length(width), len(normalized))
                widths[identifier] = width
        return cls(default_len=default_len, widths=widths)

    def width_for(self, identifier: str) -> int:
        """Display width for one identifier; unknown identifiers use the default."""
        return self.widths.get(identifier, self.default_len)


def single_id_widths(identifier: str) -> ShortIdWidths:
    """Build widths for one identifier alone (no widening, default length)."""
    return ShortIdWidths.build([identifier], DEFAULT_SHORT_ID_LENGTH)


def format_issue_key(identifier: str, project_context: bool) -> str:
    """
    Produce a display-friendly issue key.

    :param identifier: Full issue identifier (may include project key and UUID).
    :type identifier: str
    :param project_context: Whether the display is within a project context.
    :type project_context: bool
    :return: Formatted key with optional project key and abbreviated hash.
    :rtype: str
    """
    return format_issue_key_with(identifier, project_context, single_id_widths(identifier))


def format_issue_key_with(
    identifier: str, project_context: bool, short_id_widths: ShortIdWidths
) -> str:
    """
    Produce a display-friendly issue key using universe-derived widths.

    :param identifier: Full issue identifier (may include project key and UUID).
    :type identifier: str
    :param project_context: Whether the display is within a project context.
    :type project_context: bool
    :param short_id_widths: Widths derived from the project-wide identifier universe.
    :type short_id_widths: ShortIdWidths
    :return: Formatted key with optional project key and abbreviated hash.
    :rtype: str
    """
    if identifier.isdigit():
        return identifier

    key_part = ""
    remainder = identifier
    if "-" in identifier:
        parts = identifier.split("-", 1)
        if len(parts) == 2 and parts[0] and parts[1]:
            key_part, remainder = parts

    base = remainder
    suffix = ""
    if "." in remainder:
        base, tail = remainder.split(".", 1)
        suffix = f".{tail}"

    normalized = base.replace("-", "")
    width = short_id_widths.width_for(identifier)
    truncated = normalized[:width] if normalized else normalized

    if project_context:
        return f"{truncated}{suffix}"

    if key_part:
        return f"{key_part}-{truncated}{suffix}"

    return f"{truncated}{suffix}"


def matches_issue_identifier(candidate: str, full_id: str) -> bool:
    """
    Check if a candidate identifier matches a full issue identifier.

    Accepts full identifiers, project-context short ids, and abbreviated
    prefixes. Comparison is hyphen-insensitive (display strips UUID hyphens)
    and dotted sub-ID suffixes must match exactly.

    :param candidate: User-provided identifier value.
    :type candidate: str
    :param full_id: Full issue identifier from storage.
    :type full_id: str
    :return: True if the candidate matches the full identifier.
    :rtype: bool
    """
    if candidate == full_id:
        return True
    if not candidate or not full_id:
        return False

    if candidate.isdigit():
        return False

    candidate_key, candidate_base, candidate_tail = _split_identifier(candidate)
    full_key, full_base, full_tail = _split_identifier(full_id)

    if candidate_tail != full_tail and not (candidate_tail is None and full_tail is None):
        return False

    if candidate_key is not None and candidate_key != full_key:
        return False

    candidate_normalized = candidate_base.replace("-", "")
    full_normalized = full_base.replace("-", "")

    if not candidate_normalized:
        return False

    return full_normalized.startswith(candidate_normalized)


def generate_issue_identifier(request: IssueIdentifierRequest) -> IssueIdentifierResult:
    """Generate a unique issue ID using a UUID.

    :param request: Validated request containing title and existing IDs.
    :type request: IssueIdentifierRequest
    :return: A unique ID string with format '{prefix}-{uuid}'.
    :rtype: IssueIdentifierResult
    :raises RuntimeError: If unable to generate unique ID after 10 attempts.
    """
    if request.requested_id:
        if request.requested_id in request.existing_ids:
            raise ValueError(f"requested id '{request.requested_id}' already exists")
        return IssueIdentifierResult(identifier=request.requested_id)

    for _ in range(10):
        identifier = f"{request.prefix}-{_next_uuid_value()}"
        if identifier not in request.existing_ids:
            return IssueIdentifierResult(identifier=identifier)

    raise RuntimeError("unable to generate unique id after 10 attempts")


def generate_many_identifiers(title: str, prefix: str, count: int) -> Set[str]:
    """Generate multiple identifiers for uniqueness checks.

    :param title: Base title for hashing.
    :type title: str
    :param prefix: ID prefix.
    :type prefix: str
    :param count: Number of IDs to generate.
    :type count: int
    :return: Set of generated identifiers.
    :rtype: Set[str]
    """
    existing: Set[str] = set()
    for _ in range(count):
        request = IssueIdentifierRequest(
            title=title, prefix=prefix, existing_ids=existing
        )
        result = generate_issue_identifier(request)
        existing.add(result.identifier)
    return existing
