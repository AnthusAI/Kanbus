"""Kanbus CLI version requirement enforcement."""

from __future__ import annotations

import re
from pathlib import Path

SEMVER_CORE_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
SEMVER_CORE_FULL_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

INVALID_KANBUS_VERSION_MESSAGE = (
    "kanbus-version is invalid: expected a single MAJOR.MINOR.PATCH value"
)


class KanbusVersionError(RuntimeError):
    """Raised when the running CLI does not satisfy kanbus-version."""


def parse_semver_core(version: str) -> tuple[int, int, int] | None:
    """
    Parse the leading MAJOR.MINOR.PATCH from a version string.

    :param version: Raw version string, optionally followed by git-describe suffixes.
    :type version: str
    :return: Parsed core version tuple, or None when no core is present.
    :rtype: tuple[int, int, int] | None
    """
    match = SEMVER_CORE_PATTERN.match(version.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def compare_semver_cores(running: str, required: str) -> bool:
    """
    Return whether the running version satisfies the required core version.

    Git-describe suffixes on the running version are ignored. A suffix never
    satisfies a higher required patch level than the parsed core.

    :param running: Running CLI version string.
    :type running: str
    :param required: Required MAJOR.MINOR.PATCH value.
    :type required: str
    :return: True when running core is greater than or equal to required core.
    :rtype: bool
    """
    running_core = parse_semver_core(running)
    required_core = parse_semver_core(required)
    if running_core is None or required_core is None:
        return False
    return running_core >= required_core


def format_version_mismatch_error(running: str, required: str) -> str:
    """
    Build the user-facing version mismatch message.

    :param running: Running CLI version string.
    :type running: str
    :param required: Required MAJOR.MINOR.PATCH value.
    :type required: str
    :return: Error message text.
    :rtype: str
    """
    return (
        f"Kanbus CLI {running} does not satisfy this project's required version {required}.\n"
        "Upgrade: cargo install kanbus --locked --force"
    )


def format_unparseable_running_version_error(raw: str) -> str:
    """
    Build the user-facing error for an unparseable running version.

    :param raw: Raw running CLI version string.
    :type raw: str
    :return: Error message text.
    :rtype: str
    """
    return f"Kanbus CLI version '{raw}' cannot be compared with kanbus-version"


def read_required_kanbus_version(root: Path) -> str | None:
    """
    Read the required version from a root-level kanbus-version file.

    :param root: Repository root directory.
    :type root: Path
    :return: Required MAJOR.MINOR.PATCH value, or None when the file is absent.
    :rtype: str | None
    :raises KanbusVersionError: When the file exists but is empty or invalid.
    """
    version_path = root / "kanbus-version"
    if not version_path.is_file():
        return None
    content = version_path.read_text(encoding="utf-8").strip()
    if not content or not SEMVER_CORE_FULL_PATTERN.fullmatch(content):
        raise KanbusVersionError(INVALID_KANBUS_VERSION_MESSAGE)
    return content


def enforce_kanbus_version(root: Path, running_version: str) -> None:
    """
    Enforce the repository kanbus-version requirement against the running CLI.

    :param root: Repository root directory.
    :type root: Path
    :param running_version: Running CLI version string.
    :type running_version: str
    :raises KanbusVersionError: When the requirement is not satisfied.
    """
    required = read_required_kanbus_version(root)
    if required is None:
        return
    running_core = parse_semver_core(running_version)
    if running_core is None:
        raise KanbusVersionError(
            format_unparseable_running_version_error(running_version)
        )
    if not compare_semver_cores(running_version, required):
        raise KanbusVersionError(
            format_version_mismatch_error(running_version, required)
        )
