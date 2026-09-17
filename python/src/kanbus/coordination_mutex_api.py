"""HTTP client for the optional hard coordination mutex API."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlparse

from kanbus.coordination import CoordinationError
from kanbus.models import MutexApiConfiguration

REQUEST_TIMEOUT_SECONDS = 3.0
_urlopen = urllib.request.urlopen


class MutexApiUnavailable(CoordinationError):
    """The mutex API could not be reached or returned a server failure."""


class MutexApiError(CoordinationError):
    """The mutex API rejected a request or returned an invalid response."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class MutexLease:
    """Active lease data returned by the mutex API."""

    resource: str
    owner: str
    claim_id: str
    revision: int
    claimed_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class _Response:
    status: int
    body: bytes


def is_configured(configuration: MutexApiConfiguration) -> bool:
    """Return whether endpoint and bearer credentials form a usable URL config."""
    endpoint = (configuration.endpoint or "").strip()
    token = (configuration.bearer_token or "").strip()
    if not endpoint or not token:
        return False
    parsed = urlparse(endpoint)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def acquire(
    configuration: MutexApiConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    revision: int,
    ttl_seconds: int,
) -> MutexLease:
    """Acquire a lease, failing with the API's contention or validation error."""
    _validate_positive_integer(revision, "revision")
    _validate_positive_integer(ttl_seconds, "ttl_seconds")
    response = _request(
        configuration,
        "POST",
        resource,
        {
            "owner": owner,
            "claim_id": claim_id,
            "revision": revision,
            "ttl_seconds": ttl_seconds,
        },
    )
    if response.status == 409:
        raise _api_error(response, "lease already held")
    if response.status != 201:
        raise _api_error(
            response, f"mutex api acquire failed with status {response.status}"
        )
    return _parse_lease(response.body, resource)


def renew(
    configuration: MutexApiConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
    extend_seconds: int,
) -> MutexLease:
    """Extend a matching live lease."""
    _validate_positive_integer(extend_seconds, "extend_seconds")
    response = _request(
        configuration,
        "PUT",
        resource,
        {
            "owner": owner,
            "claim_id": claim_id,
            "extend_seconds": extend_seconds,
        },
    )
    if response.status in {403, 404}:
        default = "lease owner mismatch" if response.status == 403 else "no live lease"
        raise _api_error(response, default)
    if response.status != 200:
        raise _api_error(
            response, f"mutex api renew failed with status {response.status}"
        )
    return _parse_lease(response.body, resource)


def release(
    configuration: MutexApiConfiguration,
    *,
    resource: str,
    owner: str,
    claim_id: str,
) -> None:
    """Release a matching live lease."""
    response = _request(
        configuration,
        "DELETE",
        resource,
        {"owner": owner, "claim_id": claim_id},
    )
    if response.status in {403, 404}:
        default = "lease owner mismatch" if response.status == 403 else "no live lease"
        raise _api_error(response, default)
    if response.status != 204:
        raise _api_error(
            response, f"mutex api release failed with status {response.status}"
        )


def inspect(
    configuration: MutexApiConfiguration, *, resource: str
) -> MutexLease | None:
    """Return the active lease, or ``None`` when there is no live lease."""
    response = _request(configuration, "GET", resource)
    if response.status == 404:
        return None
    if response.status != 200:
        raise _api_error(
            response, f"mutex api inspect failed with status {response.status}"
        )
    lease = _parse_lease(response.body, resource)
    # The service is authoritative for acquire/renew/release.  Treat a stale
    # successful read as eligible too: direct API Gateway/DynamoDB mappings can
    # retain an expired item until DynamoDB's asynchronous TTL cleanup.
    if lease.expires_at <= datetime.now(UTC):
        return None
    return lease


def _request(
    configuration: MutexApiConfiguration,
    method: str,
    resource: str,
    body: dict[str, Any] | None = None,
) -> _Response:
    if not is_configured(configuration):
        raise MutexApiUnavailable("mutex api is not configured")
    endpoint = (configuration.endpoint or "").rstrip("/")
    url = f"{endpoint}/api/coordination/leases/{quote(resource, safe='')}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {configuration.bearer_token}",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:  # noqa: S310
            result = _Response(response.status, response.read())
            if result.status >= 500:
                raise MutexApiUnavailable(
                    _response_message(result, "mutex api unavailable")
                )
            return result
    except urllib.error.HTTPError as error:
        response = _Response(error.code, error.read())
        if response.status >= 500:
            raise MutexApiUnavailable(
                _response_message(response, "mutex api unavailable")
            ) from error
        return response
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise MutexApiUnavailable("mutex api unavailable") from error


def _api_error(response: _Response, fallback: str) -> MutexApiError:
    return MutexApiError(_response_message(response, fallback), status=response.status)


def _response_message(response: _Response, fallback: str) -> str:
    if response.body:
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            for key in ("message", "error", "detail"):
                message = payload.get(key)
                if isinstance(message, str) and message:
                    return message
    return fallback


def _parse_lease(body: bytes, requested_resource: str) -> MutexLease:
    try:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("response must be an object")
        resource = payload["resource"]
        owner = payload["owner"]
        claim_id = payload["claim_id"]
        revision = payload["revision"]
        claimed_at = _timestamp(payload["claimed_at"], "claimed_at")
        expires_at = _timestamp(payload["expires_at"], "expires_at")
        if (
            not isinstance(resource, str)
            or not isinstance(owner, str)
            or not isinstance(claim_id, str)
        ):
            raise ValueError("resource, owner, and claim_id must be strings")
        if resource != requested_resource:
            raise ValueError("response resource does not match request")
        _validate_positive_integer(revision, "revision")
        return MutexLease(
            resource=resource,
            owner=owner,
            claim_id=claim_id,
            revision=revision,
            claimed_at=claimed_at,
            expires_at=expires_at,
        )
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise MutexApiError("mutex api returned an invalid lease response") from error


def _timestamp(value: Any, field: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be Unix seconds")
    return datetime.fromtimestamp(value, UTC)


def _validate_positive_integer(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MutexApiError(f"{field} must be a positive integer")
