"""Behave steps for GitHub cloud webhook ingress."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from behave import given, then, when

_LAMBDA_DIR = Path(__file__).resolve().parents[3] / "infra" / "cloud" / "lambda"
if str(_LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(_LAMBDA_DIR))

import webhook_handler  # type: ignore  # noqa: E402


def _parse_path_tenant(path: str) -> dict[str, str] | None:
    prefix = "/internal/webhooks/github/"
    if not path.startswith(prefix):
        return None
    remainder = path.removeprefix(prefix).strip("/")
    if not remainder:
        return None
    segments = remainder.split("/")
    if len(segments) < 2:
        return None
    account = segments[0]
    project = "/".join(segments[1:])
    if not account or not project:
        return None
    return {"account": account, "project": project}


def _build_push_payload(account: str, project: str) -> dict[str, Any]:
    return {
        "ref": "refs/heads/dev",
        "after": "abc123",
        "repository": {
            "clone_url": f"https://github.com/{account}/{project}.git",
        },
    }


@given('the GitHub webhook secret is "{secret}"')
def given_webhook_secret(context: object, secret: str) -> None:
    webhook_handler._SECRET_CACHE = None
    context.webhook_secret = secret
    context.sqs_mock = MagicMock()
    context.sqs_patcher = patch.object(webhook_handler, "sqs", context.sqs_mock)
    context.secret_patcher = patch.object(
        webhook_handler, "_load_webhook_secret", return_value=secret
    )
    context.sqs_patcher.start()
    context.secret_patcher.start()


@given('the sync queue URL is "{queue_url}"')
def given_sync_queue_url(context: object, queue_url: str) -> None:
    os.environ["SYNC_QUEUE_URL"] = queue_url


@given('a signed GitHub push payload for account "{account}" and project "{project}"')
def given_signed_push_payload(context: object, account: str, project: str) -> None:
    payload = _build_push_payload(account, project)
    body = json.dumps(payload)
    digest = hmac.new(
        context.webhook_secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    context.webhook_body = body
    context.webhook_headers = {
        "X-Hub-Signature-256": f"sha256={digest}",
        "X-GitHub-Event": "push",
        "X-GitHub-Delivery": "delivery-1",
    }
    context.webhook_account = account
    context.webhook_project = project


@given(
    'a signed GitHub push payload without Kanbus headers for account "{account}" '
    'and project "{project}"'
)
def given_signed_push_without_kanbus_headers(
    context: object, account: str, project: str
) -> None:
    given_signed_push_payload(context, account, project)


@given(
    'an unsigned GitHub push payload for account "{account}" and project "{project}"'
)
def given_unsigned_push_payload(context: object, account: str, project: str) -> None:
    payload = _build_push_payload(account, project)
    body = json.dumps(payload)
    context.webhook_body = body
    context.webhook_headers = {
        "X-GitHub-Event": "push",
        "X-GitHub-Delivery": "delivery-1",
    }
    context.webhook_account = account
    context.webhook_project = project


@given('the GitHub event type is "{event_type}"')
def given_github_event_type(context: object, event_type: str) -> None:
    context.webhook_headers["X-GitHub-Event"] = event_type


@when('the webhook handler receives the push at "{path}"')
def when_webhook_handler_receives_push(context: object, path: str) -> None:
    path_params = _parse_path_tenant(path)
    event: dict[str, Any] = {
        "path": path,
        "headers": context.webhook_headers,
        "body": context.webhook_body,
        "isBase64Encoded": False,
    }
    if path_params is not None:
        event["pathParameters"] = path_params
    context.webhook_response = webhook_handler.handler(event, None)


@then("the webhook response status should be {status:d}")
def then_webhook_response_status(context: object, status: int) -> None:
    assert context.webhook_response["statusCode"] == status


@then('the webhook response body should contain "{text}"')
def then_webhook_response_body_contains(context: object, text: str) -> None:
    body = context.webhook_response["body"]
    assert text in body, f"Expected '{text}' in response body: {body}"


@then(
    'the sync queue should receive a message for account "{account}" and project "{project}"'
)
def then_sync_queue_receives_message(
    context: object, account: str, project: str
) -> None:
    context.sqs_mock.send_message.assert_called_once()
    call_kwargs = context.sqs_mock.send_message.call_args.kwargs
    message = json.loads(call_kwargs["MessageBody"])
    assert message["tenant"] == {"account": account, "project": project}
    assert message["after_sha"] == "abc123"
    assert message["ref"] == "refs/heads/dev"
