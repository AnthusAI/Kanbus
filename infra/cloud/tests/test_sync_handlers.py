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

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

sys.path.append(str(Path(__file__).resolve().parents[1] / "lambda"))

import sync_efs_writer  # type: ignore  # noqa: E402
import sync_git  # type: ignore  # noqa: E402
import sync_git_lib  # type: ignore  # noqa: E402
import webhook_handler  # type: ignore  # noqa: E402


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


class GitSyncHandlerTests(unittest.TestCase):
    """Validate git sync lambda upload behavior."""

    @patch.object(sync_git, "_s3_client")
    @patch.object(sync_git, "materialize_repo_tarball")
    def test_processes_sqs_record_uploads_tarball(
        self,
        materialize_tarball: MagicMock,
        s3_client_factory: MagicMock,
    ) -> None:
        s3_client = MagicMock()
        s3_client_factory.return_value = s3_client
        with tempfile.TemporaryDirectory() as temporary_directory:
            tarball_path = Path(temporary_directory) / "abc123.tar.gz"
            tarball_path.write_bytes(b"tarball")
            materialize_tarball.return_value = tarball_path
            os.environ["KANBUS_SYNC_BUCKET"] = "kanbus-sync-test"
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

            result = sync_git.handler(event, None)
            self.assertEqual(result["status"], "ok")
            materialize_tarball.assert_called_once()
            s3_client.put_object.assert_called_once()
            call_kwargs = s3_client.put_object.call_args.kwargs
            self.assertEqual(call_kwargs["Bucket"], "kanbus-sync-test")
            self.assertEqual(call_kwargs["Key"], "acct/proj/abc123.tar.gz")
            self.assertEqual(call_kwargs["Metadata"], {"ref": "refs/heads/dev"})

    @patch.object(sync_git_lib, "_run")
    def test_sync_repo_uses_safe_directory_flag_for_repo_commands(self, run_cmd: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory) / "acct" / "proj" / "repo"
            (repo_root / ".git").mkdir(parents=True, exist_ok=True)

            sync_git_lib.sync_repo(repo_root, "https://github.com/org/repo.git", "abc123")
            calls = [call.args[0] for call in run_cmd.call_args_list]
            self.assertIn(
                [
                    "git",
                    "-c",
                    f"safe.directory={repo_root}",
                    "remote",
                    "set-url",
                    "origin",
                    "https://github.com/org/repo.git",
                ],
                calls,
            )
            self.assertIn(
                [
                    "git",
                    "-c",
                    f"safe.directory={repo_root}",
                    "fetch",
                    "--prune",
                    "origin",
                ],
                calls,
            )
            self.assertIn(
                [
                    "git",
                    "-c",
                    f"safe.directory={repo_root}",
                    "reset",
                    "--hard",
                    "abc123",
                ],
                calls,
            )


class EfsWriterHandlerTests(unittest.TestCase):
    """Validate EFS writer extraction and IoT publish flow."""

    def test_parses_s3_key_into_tenant_coordinates(self) -> None:
        account, project, sha = sync_efs_writer.parse_tarball_object_key("acct/proj/abc123.tar.gz")
        self.assertEqual(account, "acct")
        self.assertEqual(project, "proj")
        self.assertEqual(sha, "abc123")

    @patch.object(sync_efs_writer, "_s3_client")
    @patch.object(sync_efs_writer, "publish_sync_event")
    @patch.object(sync_efs_writer, "extract_tarball_to_tenant_root")
    def test_processes_s3_record_extracts_and_publishes(
        self,
        extract_tarball: MagicMock,
        publish_event: MagicMock,
        s3_client_factory: MagicMock,
    ) -> None:
        s3_client = MagicMock()
        s3_client_factory.return_value = s3_client
        with tempfile.TemporaryDirectory() as temporary_directory:
            os.environ["KANBUS_TENANT_MOUNT"] = temporary_directory
            os.environ["KANBUS_SYNC_BUCKET"] = "kanbus-sync-test"
            s3_client.head_object.return_value = {"Metadata": {"ref": "refs/heads/dev"}}

            def download_file(_bucket: str, _key: str, destination: str) -> None:
                Path(destination).write_bytes(b"ignored")

            s3_client.download_file.side_effect = download_file

            event = {
                "Records": [
                    {
                        "s3": {
                            "bucket": {"name": "kanbus-sync-test"},
                            "object": {"key": "acct/proj/abc123.tar.gz"},
                        }
                    }
                ]
            }

            result = sync_efs_writer.handler(event, None)
            self.assertEqual(result["status"], "ok")
            extract_tarball.assert_called_once()
            publish_event.assert_called_once_with("acct", "proj", "abc123", "refs/heads/dev")


if __name__ == "__main__":
    unittest.main()
