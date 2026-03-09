from __future__ import annotations

import pytest

from kanbus import daemon_protocol


def test_parse_version_success_and_failures() -> None:
    assert daemon_protocol.parse_version("1.0") == (1, 0)
    assert daemon_protocol.parse_version("12.34") == (12, 34)

    for bad in ["1", "1.2.3", "a.b", "1.x", ""]:
        with pytest.raises(
            daemon_protocol.ProtocolError, match="invalid protocol version"
        ):
            daemon_protocol.parse_version(bad)


def test_validate_protocol_compatibility_rules() -> None:
    daemon_protocol.validate_protocol_compatibility("1.0", "1.0")
    daemon_protocol.validate_protocol_compatibility("1.1", "1.2")

    with pytest.raises(
        daemon_protocol.ProtocolError, match="protocol version mismatch"
    ):
        daemon_protocol.validate_protocol_compatibility("1.0", "2.0")

    with pytest.raises(
        daemon_protocol.ProtocolError, match="protocol version unsupported"
    ):
        daemon_protocol.validate_protocol_compatibility("1.3", "1.2")


def test_envelope_models_validate_payloads() -> None:
    req = daemon_protocol.RequestEnvelope(
        protocol_version="1.0",
        request_id="req-1",
        action="index.list",
        payload={"x": 1},
    )
    assert req.action == "index.list"

    err = daemon_protocol.ErrorEnvelope(
        code="internal", message="boom", details={"k": "v"}
    )
    resp = daemon_protocol.ResponseEnvelope(
        protocol_version="1.0",
        request_id="req-1",
        status="error",
        error=err,
    )
    assert resp.error is not None
    assert resp.error.message == "boom"
