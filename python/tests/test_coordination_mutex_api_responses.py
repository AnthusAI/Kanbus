"""Response validation and transport-error tests for the mutex HTTP client."""

from __future__ import annotations

import json
import urllib.error

import pytest

from kanbus import coordination_mutex_api
from kanbus.coordination_mutex_api import MutexApiError, MutexApiUnavailable
from kanbus.models import MutexApiConfiguration


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args) -> None:
        return None


def _configuration() -> MutexApiConfiguration:
    return MutexApiConfiguration(
        endpoint="https://mutex.example.test",
        bearer_token="only-for-the-request",
    )


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"[]", "invalid lease response"),
        (b"not-json", "invalid lease response"),
        (json.dumps({"resource": "job:1"}).encode(), "invalid lease response"),
        (
            json.dumps(
                {
                    "resource": "job:other",
                    "owner": "worker",
                    "claim_id": "claim",
                    "revision": 1,
                    "claimed_at": 100,
                    "expires_at": 200,
                }
            ).encode(),
            "invalid lease response",
        ),
        (
            json.dumps(
                {
                    "resource": "job:1",
                    "owner": "worker",
                    "claim_id": "claim",
                    "revision": True,
                    "claimed_at": 100,
                    "expires_at": 200,
                }
            ).encode(),
            "revision must be a positive integer",
        ),
        (
            json.dumps(
                {
                    "resource": "job:1",
                    "owner": "worker",
                    "claim_id": "claim",
                    "revision": 1,
                    "claimed_at": "100",
                    "expires_at": 200,
                }
            ).encode(),
            "invalid lease response",
        ),
    ],
)
def test_success_response_with_invalid_lease_data_is_rejected(
    monkeypatch,
    body: bytes,
    message: str,
) -> None:
    monkeypatch.setattr(
        coordination_mutex_api,
        "_urlopen",
        lambda *_args, **_kwargs: _Response(201, body),
    )

    with pytest.raises(MutexApiError, match=message):
        coordination_mutex_api.acquire(
            _configuration(),
            resource="job:1",
            owner="worker",
            claim_id="claim",
            revision=1,
            ttl_seconds=60,
        )


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("slow"), OSError("socket"), urllib.error.URLError("offline")],
)
def test_transport_failures_are_normalized_without_exposing_details(
    monkeypatch,
    failure: Exception,
) -> None:
    monkeypatch.setattr(
        coordination_mutex_api,
        "_urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(MutexApiUnavailable, match="mutex api unavailable") as error:
        coordination_mutex_api.inspect(_configuration(), resource="job:offline")
    assert "slow" not in str(error.value)
    assert "socket" not in str(error.value)
    assert "offline" not in str(error.value)


def test_http_5xx_is_unavailable_for_response_and_http_error_paths(monkeypatch) -> None:
    config = _configuration()
    monkeypatch.setattr(
        coordination_mutex_api,
        "_urlopen",
        lambda *_args, **_kwargs: _Response(503, b'{"detail":"service maintenance"}'),
    )
    with pytest.raises(MutexApiUnavailable, match="service maintenance"):
        coordination_mutex_api.inspect(config, resource="job:maintenance")

    def server_error(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            "https://mutex.example.test/leases/job",
            502,
            "bad gateway",
            hdrs=None,
            fp=__import__("io").BytesIO(b'{"error":"gateway unavailable"}'),
        )

    monkeypatch.setattr(coordination_mutex_api, "_urlopen", server_error)
    with pytest.raises(MutexApiUnavailable, match="gateway unavailable"):
        coordination_mutex_api.inspect(config, resource="job:gateway")


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("acquire", "mutex api acquire failed with status 202"),
        ("renew", "mutex api renew failed with status 202"),
        ("release", "mutex api release failed with status 200"),
        ("inspect", "mutex api inspect failed with status 202"),
    ],
)
def test_unexpected_success_status_is_reported_by_operation(
    monkeypatch,
    operation: str,
    expected: str,
) -> None:
    status = 200 if operation == "release" else 202
    monkeypatch.setattr(
        coordination_mutex_api,
        "_urlopen",
        lambda *_args, **_kwargs: _Response(status, b""),
    )
    method = getattr(coordination_mutex_api, operation)

    kwargs = {"resource": "job:unexpected"}
    if operation == "acquire":
        kwargs.update(owner="worker", claim_id="claim", revision=1, ttl_seconds=60)
    elif operation == "renew":
        kwargs.update(owner="worker", claim_id="claim", extend_seconds=60)
    elif operation == "release":
        kwargs.update(owner="worker", claim_id="claim")

    with pytest.raises(MutexApiError, match=expected):
        method(_configuration(), **kwargs)


def test_error_body_fallback_ignores_invalid_encoding_and_non_string_messages() -> None:
    assert (
        coordination_mutex_api._response_message(
            coordination_mutex_api._Response(400, b"\xff"), "fallback"
        )
        == "fallback"
    )
    assert (
        coordination_mutex_api._response_message(
            coordination_mutex_api._Response(400, b'{"message":42,"error":""}'),
            "fallback",
        )
        == "fallback"
    )
