"""Tests for daemon protocol parsing and validation."""

from __future__ import annotations

import pytest

from taskulus.daemon_protocol import (
    ProtocolError,
    parse_version,
    validate_protocol_compatibility,
)


def test_parse_version_parses_major_minor() -> None:
    assert parse_version("1.2") == (1, 2)


def test_parse_version_rejects_invalid_format() -> None:
    with pytest.raises(ProtocolError, match="invalid protocol version"):
        parse_version("1")


def test_parse_version_rejects_non_numeric() -> None:
    with pytest.raises(ProtocolError, match="invalid protocol version"):
        parse_version("1.x")


def test_validate_protocol_compatibility_allows_same_major() -> None:
    validate_protocol_compatibility("1.0", "1.2")


def test_validate_protocol_compatibility_rejects_major_mismatch() -> None:
    with pytest.raises(ProtocolError, match="protocol version mismatch"):
        validate_protocol_compatibility("2.0", "1.0")


def test_validate_protocol_compatibility_rejects_newer_client() -> None:
    with pytest.raises(ProtocolError, match="protocol version unsupported"):
        validate_protocol_compatibility("1.2", "1.1")
