"""AWS IoT custom authorizer for Kanbus CLI MQTT API tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs

import boto3

_TOKEN_TABLE = os.environ["KANBUS_TOKEN_TABLE"]
_PEPPER_SECRET_ARN = os.environ["KANBUS_TOKEN_PEPPER_SECRET_ARN"]
_AWS_ACCOUNT = os.environ.get("KANBUS_AWS_ACCOUNT", "")
_AWS_REGION = os.environ.get("KANBUS_AWS_REGION", os.environ.get("AWS_REGION", "us-east-1"))

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_TOKEN_TABLE)
_secrets = boto3.client("secretsmanager")
_PEPPER_CACHE: str | None = None


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
    return hashlib.sha256(f"{pepper}:{raw_secret}".encode("utf-8")).hexdigest()


def _decode_password(raw_password: str | None) -> str | None:
    if not raw_password:
        return None
    try:
        return base64.b64decode(raw_password).decode("utf-8")
    except Exception:
        return raw_password


def _extract_token(event: dict[str, Any]) -> str | None:
    if isinstance(event.get("token"), str):
        return str(event["token"])

    protocol_data = event.get("protocolData") or {}
    mqtt_data = protocol_data.get("mqtt") or {}

    decoded_password = _decode_password(mqtt_data.get("password"))
    if decoded_password:
        return decoded_password

    username = mqtt_data.get("username")
    if isinstance(username, str):
        query = username[1:] if username.startswith("?") else username
        params = parse_qs(query)
        token = params.get("token")
        if token and token[0]:
            return token[0]
    return None


def _parse_token(token_value: str) -> tuple[str, str] | None:
    if not token_value.startswith("kbt_") or "." not in token_value:
        return None
    left, secret = token_value.split(".", 1)
    token_id = left.removeprefix("kbt_").strip()
    if not token_id or not secret:
        return None
    return token_id, secret


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return True
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return datetime.now(UTC) >= parsed


def _policy_document(account: str, project: str, scopes: list[str]) -> dict[str, Any]:
    statements: list[dict[str, Any]] = [
        {
            "Effect": "Allow",
            "Action": ["iot:Connect"],
            "Resource": [f"arn:aws:iot:{_AWS_REGION}:{_AWS_ACCOUNT}:client/*"],
        }
    ]

    can_read = any(scope in {"read", "subscribe"} for scope in scopes)
    can_publish = "publish" in scopes
    topic_arn = f"arn:aws:iot:{_AWS_REGION}:{_AWS_ACCOUNT}:topic/projects/{account}/{project}/events"
    topic_filter_arn = (
        f"arn:aws:iot:{_AWS_REGION}:{_AWS_ACCOUNT}:topicfilter/projects/{account}/{project}/events"
    )

    if can_read:
        statements.append(
            {
                "Effect": "Allow",
                "Action": ["iot:Subscribe"],
                "Resource": [topic_filter_arn],
            }
        )
        statements.append(
            {
                "Effect": "Allow",
                "Action": ["iot:Receive"],
                "Resource": [topic_arn],
            }
        )
    if can_publish:
        statements.append(
            {
                "Effect": "Allow",
                "Action": ["iot:Publish"],
                "Resource": [topic_arn],
            }
        )
    return {"Version": "2012-10-17", "Statement": statements}


def _deny(reason: str) -> dict[str, Any]:
    return {"isAuthenticated": False, "disconnectAfterInSeconds": 60, "reason": reason}


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        token_value = _extract_token(event)
        if not token_value:
            return _deny("missing token")
        parsed = _parse_token(token_value)
        if not parsed:
            return _deny("invalid token format")
        token_id, token_secret = parsed

        response = _table.get_item(Key={"token_id": token_id})
        item = response.get("Item")
        if not item:
            return _deny("token not found")
        if bool(item.get("revoked", False)):
            return _deny("token revoked")
        if _is_expired(item.get("expires_at")):
            return _deny("token expired")

        expected_hash = str(item.get("secret_hash", ""))
        if not expected_hash:
            return _deny("token hash missing")
        provided_hash = _hash_secret(token_secret)
        if not hmac.compare_digest(expected_hash, provided_hash):
            return _deny("token hash mismatch")

        account = str(item.get("account", "")).strip()
        project = str(item.get("project", "")).strip()
        if not account or not project:
            return _deny("token tenant scope missing")
        scopes = [str(scope).strip() for scope in item.get("scopes", [])]
        if not scopes:
            scopes = ["subscribe"]

        return {
            "isAuthenticated": True,
            "principalId": f"{account}:{project}:{token_id}",
            "policyDocuments": [_policy_document(account, project, scopes)],
            "disconnectAfterInSeconds": 86_400,
            "refreshAfterInSeconds": 300,
            "context": {
                "account": account,
                "project": project,
                "token_id": token_id,
                "scopes": json.dumps(scopes),
            },
        }
    except Exception as error:  # pragma: no cover - defensive
        return _deny(str(error))
