"""Admin API for Kanbus MQTT API token lifecycle management."""

from __future__ import annotations

import hashlib
import base64
import json
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

_TOKEN_TABLE = os.environ["KANBUS_TOKEN_TABLE"]
_PEPPER_SECRET_ARN = os.environ["KANBUS_TOKEN_PEPPER_SECRET_ARN"]
_ADMIN_GROUP = os.environ.get("KANBUS_ADMIN_GROUP", "kanbus-admin")

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_TOKEN_TABLE)
_secrets = boto3.client("secretsmanager")
_PEPPER_CACHE: str | None = None


def _response(status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        "body": json.dumps(payload),
    }


def _load_pepper() -> str:
    global _PEPPER_CACHE  # noqa: PLW0603
    if _PEPPER_CACHE:
        return _PEPPER_CACHE
    response = _secrets.get_secret_value(SecretId=_PEPPER_SECRET_ARN)
    secret = response.get("SecretString", "")
    if not secret:
        raise RuntimeError("token pepper secret is empty")
    _PEPPER_CACHE = secret
    return secret


def _hash_secret(raw_secret: str) -> str:
    pepper = _load_pepper()
    iterations = max(int(os.environ.get("KANBUS_TOKEN_HASH_ITERATIONS", "210000")), 100000)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        raw_secret.encode("utf-8"),
        pepper.encode("utf-8"),
        iterations,
        dklen=32,
    )
    digest = base64.urlsafe_b64encode(derived).decode("utf-8").rstrip("=")
    return f"pbkdf2_sha256_v1${iterations}${digest}"


def _claims(event: dict[str, Any]) -> dict[str, str]:
    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})
    claims = authorizer.get("claims", {})
    return claims if isinstance(claims, dict) else {}


def _is_admin(claims: dict[str, str]) -> bool:
    groups = claims.get("cognito:groups", "")
    return _ADMIN_GROUP in [item.strip() for item in groups.split(",") if item.strip()]


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body")
    if not body:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _extract_method(event: dict[str, Any]) -> str:
    return str(event.get("httpMethod", "")).upper()


def _create_token(event: dict[str, Any], claims: dict[str, str]) -> dict[str, Any]:
    payload = _parse_body(event)
    account = str(payload.get("account", "")).strip()
    project = str(payload.get("project", "")).strip()
    if not account or not project:
        return _response(400, {"error": "account and project are required"})

    scopes = payload.get("scopes") or ["subscribe"]
    if not isinstance(scopes, list) or not scopes:
        return _response(400, {"error": "scopes must be a non-empty list"})
    scopes = [str(scope).strip() for scope in scopes if str(scope).strip()]
    if not scopes:
        return _response(400, {"error": "scopes must contain values"})

    expires_in_days = int(payload.get("expires_in_days", 90))
    expires_in_days = max(1, min(expires_in_days, 365))
    created_at = datetime.now(UTC)
    expires_at = created_at + timedelta(days=expires_in_days)

    token_id = uuid.uuid4().hex
    token_secret = secrets.token_urlsafe(32)
    token_value = f"kbt_{token_id}.{token_secret}"
    item = {
        "token_id": token_id,
        "account": account,
        "project": project,
        "scopes": scopes,
        "secret_hash": _hash_secret(token_secret),
        "revoked": False,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "created_by": claims.get("email") or claims.get("cognito:username") or "unknown",
    }
    _table.put_item(Item=item)

    return _response(
        201,
        {
            "token_id": token_id,
            "token": token_value,
            "account": account,
            "project": project,
            "scopes": scopes,
            "created_at": item["created_at"],
            "expires_at": item["expires_at"],
            "revoked": False,
        },
    )


def _list_tokens(event: dict[str, Any]) -> dict[str, Any]:
    params = event.get("queryStringParameters") or {}
    account = str(params.get("account", "")).strip()
    project = str(params.get("project", "")).strip()
    scan = _table.scan()
    items = scan.get("Items", [])

    filtered: list[dict[str, Any]] = []
    for item in items:
        if account and item.get("account") != account:
            continue
        if project and item.get("project") != project:
            continue
        filtered.append(
            {
                "token_id": item.get("token_id"),
                "account": item.get("account"),
                "project": item.get("project"),
                "scopes": item.get("scopes", []),
                "created_at": item.get("created_at"),
                "expires_at": item.get("expires_at"),
                "revoked": bool(item.get("revoked", False)),
                "revoked_at": item.get("revoked_at"),
            }
        )
    filtered.sort(key=lambda token: token.get("created_at") or "", reverse=True)
    return _response(200, {"tokens": filtered, "count": len(filtered), "at": _now_iso()})


def _revoke_token(event: dict[str, Any]) -> dict[str, Any]:
    path_params = event.get("pathParameters") or {}
    token_id = str(path_params.get("token_id", "")).strip()
    if not token_id:
        return _response(400, {"error": "token_id is required"})
    if token_id.startswith("kbt_"):
        token_id = token_id.removeprefix("kbt_")

    try:
        _table.update_item(
            Key={"token_id": token_id},
            UpdateExpression="SET revoked = :revoked, revoked_at = :revoked_at",
            ConditionExpression="attribute_exists(token_id)",
            ExpressionAttributeValues={
                ":revoked": True,
                ":revoked_at": _now_iso(),
            },
        )
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            return _response(404, {"error": "token not found"})
        raise
    return _response(200, {"token_id": token_id, "revoked": True})


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        claims = _claims(event)
        if not _is_admin(claims):
            return _response(403, {"error": "admin group membership required"})

        method = _extract_method(event)
        path = str(event.get("path", ""))
        if method == "POST" and path.endswith("/revoke"):
            return _revoke_token(event)
        if method == "POST":
            return _create_token(event, claims)
        if method == "GET":
            return _list_tokens(event)
        return _response(405, {"error": "method not allowed"})
    except Exception as error:  # pragma: no cover - defensive
        return _response(500, {"error": str(error)})
