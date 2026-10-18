from __future__ import annotations

import json
from pathlib import Path

import pytest

from kanbus.router_conversation import redact_text

SHARED_CASES = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "parity"
        / "redaction_cases.json"
    ).read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "case", SHARED_CASES, ids=[case["name"] for case in SHARED_CASES]
)
def test_redaction_matches_the_cases_shared_with_the_rust_runtime(case) -> None:
    assert redact_text(case["input"]) == case["expected"]
