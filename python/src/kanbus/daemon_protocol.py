"""IPC protocol models and version checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field

PROTOCOL_VERSION = "1.0"


class ProtocolError(RuntimeError):
    """Raised when protocol validation fails."""


class RequestEnvelope(BaseModel):
    """Client request envelope for daemon IPC."""

    protocol_version: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    payload: Dict[str, Any]


class ErrorEnvelope(BaseModel):
    """Structured error payload for daemon responses."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: Dict[str, Any] = Field(default_factory=dict)


class ResponseEnvelope(BaseModel):
    """Daemon response envelope for IPC."""

    protocol_version: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    result: Optional[Dict[str, Any]] = None
    error: Optional[ErrorEnvelope] = None


@dataclass(frozen=True)
class ProtocolVersions:
    """Parsed protocol versions."""

    client: Tuple[int, int]
    daemon: Tuple[int, int]


def parse_version(version: str) -> Tuple[int, int]:
    """Parse a protocol version string into a major/minor tuple.

    :param version: Version string in MAJOR.MINOR form.
    :type version: str
    :return: Parsed (major, minor) version.
    :rtype: tuple[int, int]
    :raises ProtocolError: If the version is invalid.
    """
    parts = version.split(".")
    if len(parts) != 2:
        raise ProtocolError("invalid protocol version")
    try:
        major = int(parts[0])
        minor = int(parts[1])
    except ValueError as error:
        raise ProtocolError("invalid protocol version") from error
    return major, minor


def validate_protocol_compatibility(client_version: str, daemon_version: str) -> None:
    """Validate protocol compatibility rules.

    :param client_version: Client protocol version string.
    :type client_version: str
    :param daemon_version: Daemon protocol version string.
    :type daemon_version: str
    :raises ProtocolError: If versions are incompatible.
    """
    client_major, client_minor = parse_version(client_version)
    daemon_major, daemon_minor = parse_version(daemon_version)
    if client_major != daemon_major:
        raise ProtocolError("protocol version mismatch")
    if client_minor > daemon_minor:
        raise ProtocolError("protocol version unsupported")
