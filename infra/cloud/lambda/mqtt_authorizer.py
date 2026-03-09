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
_COGNITO_USER_POOL_ID = os.environ.get("KANBUS_COGNITO_USER_POOL_ID", "")
_TENANT_ACCOUNT_CLAIM_KEY = os.environ.get("KANBUS_TENANT_ACCOUNT_CLAIM_KEY", "custom:account")
_TENANT_PROJECT_CLAIM_KEY = os.environ.get("KANBUS_TENANT_PROJECT_CLAIM_KEY", "custom:project")
_HASH_SCHEME = "pbkdf2_sha256_v1"
_HASH_ITERATIONS = max(int(os.environ.get("KANBUS_TOKEN_HASH_ITERATIONS", "210000")), 100000)
_HASH_BYTES = 32

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(_TOKEN_TABLE)
_secrets = boto3.client("secretsmanager")
_cognito = boto3.client("cognito-idp")
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
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        raw_secret.encode("utf-8"),
        pepper.encode("utf-8"),
        _HASH_ITERATIONS,
        dklen=_HASH_BYTES,
    )
    encoded = base64.urlsafe_b64encode(derived).decode("utf-8").rstrip("=")
    return f"{_HASH_SCHEME}${_HASH_ITERATIONS}${encoded}"


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


def _looks_like_jwt(token_value: str) -> bool:
    return token_value.count(".") == 2


def _decode_jwt_claims(token_value: str) -> dict[str, Any] | None:
    if not _looks_like_jwt(token_value):
        return None
    parts = token_value.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    padding = "=" * ((4 - len(payload) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(f"{payload}{padding}".encode("utf-8"))
        parsed = json.loads(decoded.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _tenant_from_cognito_access_token(access_token: str) -> tuple[str, str, str] | None:
    claims = _decode_jwt_claims(access_token)
    if claims:
        account = str(claims.get(_TENANT_ACCOUNT_CLAIM_KEY, "")).strip()
        project = str(claims.get(_TENANT_PROJECT_CLAIM_KEY, "")).strip()
        username = (
            str(claims.get("cognito:username", "")).strip()
            or str(claims.get("username", "")).strip()
            or str(claims.get("sub", "")).strip()
            or "cognito-user"
        )
        if account and project:
            return account, project, username
    if not _COGNITO_USER_POOL_ID:
        return None
    try:
        user = _cognito.get_user(AccessToken=access_token)
    except Exception:
        return None
    attributes = {
        str(attr.get("Name")): str(attr.get("Value", ""))
        for attr in user.get("UserAttributes", [])
    }
    account = attributes.get(_TENANT_ACCOUNT_CLAIM_KEY, "").strip()
    project = attributes.get(_TENANT_PROJECT_CLAIM_KEY, "").strip()
    username = str(user.get("Username", "")).strip() or "cognito-user"
    if not account or not project:
        return None
    return account, project, username


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


def _principal_id(*parts: str) -> str:
    raw = "".join(parts)
    filtered = "".join(ch for ch in raw if ch.isalnum())
    if not filtered:
        return "kanbusprincipal"
    return filtered[:128]


def _deny(reason: str) -> dict[str, Any]:
    print(json.dumps({"level": "warn", "result": "deny", "reason": reason}))
    return {"isAuthenticated": False, "disconnectAfterInSeconds": 60, "reason": reason}


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    try:
        token_value = _extract_token(event)
        if not token_value:
            return _deny("missing token")
        if _looks_like_jwt(token_value):
            tenant = _tenant_from_cognito_access_token(token_value)
            if not tenant:
                return _deny("invalid cognito access token")
            account, project, username = tenant
            scopes = ["subscribe"]
            print(
                json.dumps(
                    {
                        "level": "info",
                        "result": "allow",
                        "source": "cognito_access_token",
                    }
                )
            )
            return {
                "isAuthenticated": True,
                "principalId": _principal_id("cog", account, project, username),
                "policyDocuments": [_policy_document(account, project, scopes)],
                "disconnectAfterInSeconds": 3600,
                "refreshAfterInSeconds": 300,
                "context": {
                    "account": account,
                    "project": project,
                    "source": "cognito_access_token",
                    "scopes": json.dumps(scopes),
                },
            }
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
        print(
            json.dumps(
                {
                    "level": "info",
                    "result": "allow",
                    "source": "api_token",
                }
            )
        )

        return {
            "isAuthenticated": True,
            "principalId": _principal_id("tok", account, project, token_id),
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
