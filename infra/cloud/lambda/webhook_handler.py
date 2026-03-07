"""GitHub webhook ingress for Kanbus cloud sync queue."""

import hashlib
import hmac
import json
import os
from typing import Any

import boto3

sqs = boto3.client("sqs")


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _header(headers: dict[str, str], key: str) -> str | None:
    return headers.get(key) or headers.get(key.lower())


def _verify_signature(secret: str, payload: bytes, signature_header: str | None) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    queue_url = os.environ["SYNC_QUEUE_URL"]
    secret = os.environ["GITHUB_WEBHOOK_SECRET"]
    headers = event.get("headers") or {}
    body_text = event.get("body") or ""

    if event.get("isBase64Encoded"):
        import base64

        payload = base64.b64decode(body_text)
    else:
        payload = body_text.encode("utf-8")

    signature = _header(headers, "X-Hub-Signature-256")
    if not _verify_signature(secret, payload, signature):
        return _response(401, {"error": "invalid signature"})

    event_type = _header(headers, "X-GitHub-Event") or ""
    if event_type != "push":
        return _response(202, {"status": "ignored", "reason": f"event={event_type}"})

    account = _header(headers, "X-Kanbus-Account")
    project = _header(headers, "X-Kanbus-Project")
    if not account or not project:
        return _response(400, {"error": "missing X-Kanbus-Account or X-Kanbus-Project"})

    payload_json = json.loads(payload.decode("utf-8"))
    repo = payload_json.get("repository") or {}
    message = {
        "tenant": {"account": account, "project": project},
        "repo_url": repo.get("clone_url") or repo.get("ssh_url"),
        "ref": payload_json.get("ref"),
        "after_sha": payload_json.get("after"),
        "delivery_id": _header(headers, "X-GitHub-Delivery"),
    }

    sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message))
    return _response(202, {"status": "queued"})
