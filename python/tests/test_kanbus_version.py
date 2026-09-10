from __future__ import annotations

from pathlib import Path

import pytest

from kanbus.kanbus_version import (
    INVALID_KANBUS_VERSION_MESSAGE,
    KanbusVersionError,
    compare_semver_cores,
    enforce_kanbus_version,
    format_unparseable_running_version_error,
    read_required_kanbus_version,
)


@pytest.mark.parametrize(
    ("running", "required", "expected"),
    [
        ("0.19.1-5-gabc", "0.19.1", True),
        ("0.18.3-29-g36a5204", "0.19.1", False),
        ("0.19.1", "0.19.1", True),
        ("0.20.0", "0.19.1", True),
        ("0.19.0", "0.19.1", False),
        ("0.19.1", "0.19.0", True),
    ],
)
def test_compare_semver_cores(running: str, required: str, expected: bool) -> None:
    assert compare_semver_cores(running, required) is expected


def test_read_required_kanbus_version_missing_file(tmp_path: Path) -> None:
    assert read_required_kanbus_version(tmp_path) is None


def test_read_required_kanbus_version_invalid_file(tmp_path: Path) -> None:
    (tmp_path / "kanbus-version").write_text("not-a-version\n", encoding="utf-8")
    with pytest.raises(KanbusVersionError, match=INVALID_KANBUS_VERSION_MESSAGE):
        read_required_kanbus_version(tmp_path)


def test_enforce_kanbus_version_unparseable_running_version(tmp_path: Path) -> None:
    (tmp_path / "kanbus-version").write_text("1.0.0\n", encoding="utf-8")
    with pytest.raises(
        KanbusVersionError,
        match=format_unparseable_running_version_error("release-candidate"),
    ):
        enforce_kanbus_version(tmp_path, "release-candidate")
