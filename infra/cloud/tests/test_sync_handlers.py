"""Unit tests for cloud sync lambda handlers."""

import hashlib
import hmac
import io
import json
import os
import sys
import tarfile
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
import sync_iot_publish  # type: ignore  # noqa: E402
import sync_notify  # type: ignore  # noqa: E402
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
    """Validate EFS writer extraction and completion marker flow."""

    def test_parses_s3_key_into_tenant_coordinates(self) -> None:
        account, project, sha = sync_git_lib.parse_tarball_object_key("acct/proj/abc123.tar.gz")
        self.assertEqual(account, "acct")
        self.assertEqual(project, "proj")
        self.assertEqual(sha, "abc123")

    @patch.object(sync_efs_writer, "_s3_client")
    @patch.object(sync_efs_writer, "write_completion_marker")
    @patch.object(sync_efs_writer, "extract_tarball_to_tenant_root")
    def test_processes_s3_record_extracts_and_writes_marker(
        self,
        extract_tarball: MagicMock,
        write_marker: MagicMock,
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
            write_marker.assert_called_once_with(
                "kanbus-sync-test",
                "acct",
                "proj",
                "abc123",
                "refs/heads/dev",
            )

    @patch.object(sync_efs_writer, "_s3_client")
    def test_writes_completion_marker_with_expected_payload(self, s3_client_factory: MagicMock) -> None:
        s3_client = MagicMock()
        s3_client_factory.return_value = s3_client

        sync_efs_writer.write_completion_marker(
            "kanbus-sync-test",
            "acct",
            "proj",
            "abc123",
            "refs/heads/dev",
        )

        s3_client.put_object.assert_called_once()
        call_kwargs = s3_client.put_object.call_args.kwargs
        self.assertEqual(call_kwargs["Bucket"], "kanbus-sync-test")
        self.assertEqual(call_kwargs["Key"], "acct/proj/abc123.synced.json")
        self.assertEqual(
            json.loads(call_kwargs["Body"].decode("utf-8")),
            {
                "type": "cloud_sync_completed",
                "account": "acct",
                "project": "proj",
                "ref": "refs/heads/dev",
                "sha": "abc123",
            },
        )

    def test_extract_tarball_keeps_members_inside_tenant_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            tenant_root = Path(temporary_directory) / "acct" / "proj"
            tarball_path = Path(temporary_directory) / "abc123.tar.gz"
            with tarfile.open(tarball_path, "w:gz") as archive:
                repo_file = Path(temporary_directory) / "repo-file.txt"
                repo_file.write_text("synced", encoding="utf-8")
                archive.add(repo_file, arcname="repo/repo-file.txt")

            sync_efs_writer.extract_tarball_to_tenant_root(tarball_path, tenant_root)

            self.assertEqual((tenant_root / "repo" / "repo-file.txt").read_text(encoding="utf-8"), "synced")

    def test_extract_tarball_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            tenant_root = Path(temporary_directory) / "acct" / "proj"
            tarball_path = Path(temporary_directory) / "evil.tar.gz"
            with tarfile.open(tarball_path, "w:gz") as archive:
                member = tarfile.TarInfo(name="../escape.txt")
                member.size = 4
                archive.addfile(member, io.BytesIO(b"evil"))

            with self.assertRaises(ValueError):
                sync_efs_writer.extract_tarball_to_tenant_root(tarball_path, tenant_root)


class SyncNotifyHandlerTests(unittest.TestCase):
    """Validate sync notify marker handling and IoT publish flow."""

    def test_parses_completion_marker_key(self) -> None:
        account, project, sha = sync_git_lib.parse_completion_marker_key(
            "acct/proj/abc123.synced.json"
        )
        self.assertEqual(account, "acct")
        self.assertEqual(project, "proj")
        self.assertEqual(sha, "abc123")

    @patch.object(sync_notify, "publish_sync_event")
    @patch.object(sync_notify, "_tarball_exists")
    @patch.object(sync_notify, "_load_marker_payload")
    def test_processes_marker_and_publishes_iot(
        self,
        load_marker: MagicMock,
        tarball_exists: MagicMock,
        publish_event: MagicMock,
    ) -> None:
        load_marker.return_value = {
            "type": "cloud_sync_completed",
            "account": "acct",
            "project": "proj",
            "ref": "refs/heads/dev",
            "sha": "abc123",
        }
        tarball_exists.return_value = True
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "kanbus-sync-test"},
                        "object": {"key": "acct/proj/abc123.synced.json"},
                    }
                }
            ]
        }

        result = sync_notify.handler(event, None)
        self.assertEqual(result["status"], "ok")
        publish_event.assert_called_once_with("acct", "proj", "abc123", "refs/heads/dev")

    @patch.object(sync_notify, "publish_sync_event")
    @patch.object(sync_notify, "_tarball_exists")
    @patch.object(sync_notify, "_load_marker_payload")
    def test_missing_tarball_blocks_iot_publish(
        self,
        load_marker: MagicMock,
        tarball_exists: MagicMock,
        publish_event: MagicMock,
    ) -> None:
        load_marker.return_value = {
            "type": "cloud_sync_completed",
            "account": "acct",
            "project": "proj",
            "ref": "refs/heads/dev",
            "sha": "abc123",
        }
        tarball_exists.return_value = False
        event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": "kanbus-sync-test"},
                        "object": {"key": "acct/proj/abc123.synced.json"},
                    }
                }
            ]
        }

        with self.assertRaises(ValueError):
            sync_notify.handler(event, None)
        publish_event.assert_not_called()

    @patch.object(sync_notify, "_s3_client")
    def test_tarball_exists_treats_not_found_as_absent(self, s3_client_factory: MagicMock) -> None:
        from botocore.exceptions import ClientError

        s3_client = MagicMock()
        s3_client_factory.return_value = s3_client
        s3_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )

        self.assertFalse(sync_notify._tarball_exists("kanbus-sync-test", "acct", "proj", "abc123"))

    @patch.object(sync_notify, "_s3_client")
    def test_tarball_exists_reraises_other_client_errors(self, s3_client_factory: MagicMock) -> None:
        from botocore.exceptions import ClientError

        s3_client = MagicMock()
        s3_client_factory.return_value = s3_client
        s3_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
            "HeadObject",
        )

        with self.assertRaises(ClientError):
            sync_notify._tarball_exists("kanbus-sync-test", "acct", "proj", "abc123")


class SyncIotPublishTests(unittest.TestCase):
    """Validate IoT publish payload shape."""

    @patch("sync_iot_publish.boto3.client")
    def test_publish_sync_event_uses_expected_topic_and_payload(self, boto_client: MagicMock) -> None:
        iot_data = MagicMock()
        boto_client.return_value = iot_data
        os.environ["KANBUS_IOT_DATA_ENDPOINT"] = "iot.example.amazonaws.com"

        sync_iot_publish.publish_sync_event("acct", "proj", "abc123", "refs/heads/dev")

        boto_client.assert_called_once_with(
            "iot-data",
            endpoint_url="https://iot.example.amazonaws.com",
        )
        iot_data.publish.assert_called_once()
        call_kwargs = iot_data.publish.call_args.kwargs
        self.assertEqual(call_kwargs["topic"], "projects/acct/proj/events")
        self.assertEqual(
            json.loads(call_kwargs["payload"].decode("utf-8")),
            {
                "type": "cloud_sync_completed",
                "account": "acct",
                "project": "proj",
                "ref": "refs/heads/dev",
                "sha": "abc123",
            },
        )


if __name__ == "__main__":
    unittest.main()
