"""Unit tests for cloud sync lambda handlers."""

import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "lambda"))

import webhook_handler  # type: ignore  # noqa: E402
import sync_worker  # type: ignore  # noqa: E402


class WebhookHandlerTests(unittest.TestCase):
    """Validate webhook ingress behavior."""

    def setUp(self) -> None:
        webhook_handler._SECRET_CACHE = None

    def _signed_event(self, secret: str, payload: dict) -> dict:
        body = json.dumps(payload)
        digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
        return {
            "headers": {
                "X-Hub-Signature-256": f"sha256={digest}",
                "X-GitHub-Event": "push",
                "X-Kanbus-Account": "acct",
                "X-Kanbus-Project": "proj",
                "X-GitHub-Delivery": "delivery-1",
            },
            "body": body,
            "isBase64Encoded": False,
        }

    @patch.object(webhook_handler, "sqs")
    @patch.object(webhook_handler, "_load_webhook_secret")
    def test_queues_valid_push_event(self, load_secret: MagicMock, sqs_client: MagicMock) -> None:
        load_secret.return_value = "secret"
        os.environ["SYNC_QUEUE_URL"] = "https://example.queue/url"
        event = self._signed_event(
            "secret",
            {
                "ref": "refs/heads/dev",
                "after": "abc123",
                "repository": {"clone_url": "https://github.com/org/repo.git"},
            },
        )

        response = webhook_handler.handler(event, None)
        self.assertEqual(response["statusCode"], 202)
        sqs_client.send_message.assert_called_once()

    @patch.object(webhook_handler, "_load_webhook_secret")
    def test_rejects_invalid_tenant_headers(self, load_secret: MagicMock) -> None:
        load_secret.return_value = "secret"
        os.environ["SYNC_QUEUE_URL"] = "https://example.queue/url"
        event = self._signed_event(
            "secret",
            {
                "ref": "refs/heads/dev",
                "after": "abc123",
                "repository": {"clone_url": "https://github.com/org/repo.git"},
            },
        )
        event["headers"]["X-Kanbus-Project"] = "bad/project"

        response = webhook_handler.handler(event, None)
        self.assertEqual(response["statusCode"], 400)
        self.assertIn("invalid tenant", response["body"])


class SyncWorkerTests(unittest.TestCase):
    """Validate sync worker command and publish flow."""

    @patch.object(sync_worker, "_publish_sync_event")
    @patch.object(sync_worker, "_sync_repo")
    def test_processes_single_record(self, sync_repo: MagicMock, publish_event: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["KANBUS_TENANT_MOUNT"] = tmp
            event = {
                "Records": [
                    {
                        "body": json.dumps(
                            {
                                "tenant": {"account": "acct", "project": "proj"},
                                "repo_url": "https://github.com/org/repo.git",
                                "after_sha": "abc123",
                                "ref": "refs/heads/dev",
                            }
                        )
                    }
                ]
            }

            result = sync_worker.handler(event, None)
            self.assertEqual(result["status"], "ok")
            sync_repo.assert_called_once()
            publish_event.assert_called_once_with("acct", "proj", "abc123", "refs/heads/dev")


if __name__ == "__main__":
    unittest.main()
