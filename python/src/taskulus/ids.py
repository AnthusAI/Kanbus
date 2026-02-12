"""
Issue identifier generation.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Set

from pydantic import BaseModel, Field


class IssueIdentifierRequest(BaseModel):
    """
    Request to generate a unique issue identifier.

    :param title: The issue title to hash.
    :type title: str
    :param existing_ids: Set of existing IDs to avoid collisions.
    :type existing_ids: Set[str]
    :param prefix: ID prefix from configuration.
    :type prefix: str
    :param created_at: Timestamp used as part of the hash.
    :type created_at: datetime
    """

    title: str = Field(min_length=1)
    existing_ids: Set[str] = Field(default_factory=set)
    prefix: str = Field(default="tsk", min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class IssueIdentifierResult:
    """Result of issue identifier generation."""

    identifier: str


def _hash_identifier_material(
    title: str, created_at: datetime, random_bytes: bytes
) -> str:
    material = f"{title}{created_at.isoformat()}".encode("utf-8") + random_bytes
    return hashlib.sha256(material).hexdigest()[:6]


def generate_issue_identifier(request: IssueIdentifierRequest) -> IssueIdentifierResult:
    """Generate a unique issue ID using SHA256 hash.

    :param request: Validated request containing title and existing IDs.
    :type request: IssueIdentifierRequest
    :return: A unique ID string with format '{prefix}-{6hex}'.
    :rtype: IssueIdentifierResult
    :raises RuntimeError: If unable to generate unique ID after 10 attempts.
    """
    test_bytes_hex = os.getenv("TASKULUS_TEST_RANDOM_BYTES", "")
    test_bytes = None
    if test_bytes_hex:
        try:
            test_bytes = bytes.fromhex(test_bytes_hex)
        except ValueError as error:
            raise RuntimeError("invalid TASKULUS_TEST_RANDOM_BYTES") from error

    for _ in range(10):
        digest = _hash_identifier_material(
            request.title,
            request.created_at,
            test_bytes if test_bytes is not None else secrets.token_bytes(8),
        )
        identifier = f"{request.prefix}-{digest}"
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
