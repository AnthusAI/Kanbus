"""Unit tests for sync dispatcher and worker handlers."""

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

with patch("boto3.client", return_value=MagicMock()):
    import sync_dispatcher  # type: ignore  # noqa: E402
    import sync_worker  # type: ignore  # noqa: E402
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


class SyncWorkerTests(unittest.TestCase):
    """Validate sync worker command and publish flow."""

    @patch.object(sync_worker, "_publish_sync_event")
    @patch.object(sync_worker, "_sync_repo")
    def test_process_job_runs_git_and_publish(self, sync_repo: MagicMock, publish_event: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["KANBUS_TENANT_MOUNT"] = tmp
            body = {
                "tenant": {"account": "acct", "project": "proj"},
                "repo_url": "https://github.com/org/repo.git",
                "after_sha": "abc123",
                "ref": "refs/heads/dev",
            }

            sync_worker.process_job(body)
            sync_repo.assert_called_once()
            publish_event.assert_called_once_with("acct", "proj", "abc123", "refs/heads/dev")

    @patch.object(sync_worker, "process_job")
    def test_main_reads_sync_job_json(self, process_job: MagicMock) -> None:
        os.environ["SYNC_JOB_JSON"] = json.dumps({"tenant": {"account": "a", "project": "p"}})
        sync_worker.main()
        process_job.assert_called_once()

    @patch.object(sync_worker, "_run")
    def test_sync_repo_uses_safe_directory_flag_for_repo_commands(self, run_cmd: MagicMock) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "acct" / "proj" / "repo"
            (repo_root / ".git").mkdir(parents=True, exist_ok=True)

            sync_worker._sync_repo(repo_root, "https://github.com/org/repo.git", "abc123")
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
                ["git", "-c", f"safe.directory={repo_root}", "fetch", "--prune", "origin"],
                calls,
            )
            self.assertIn(
                ["git", "-c", f"safe.directory={repo_root}", "reset", "--hard", "abc123"],
                calls,
            )


class SyncDispatcherTests(unittest.TestCase):
    """Validate sync dispatcher RunTask wiring."""

    def setUp(self) -> None:
        os.environ["ECS_CLUSTER_NAME"] = "kanbus-tenant-sync-test"
        os.environ["ECS_TASK_DEFINITION"] = "arn:aws:ecs:us-east-1:123456789012:task-definition/test:1"
        os.environ["ECS_CONTAINER_NAME"] = "TenantSyncTask"
        os.environ["ECS_SUBNET_IDS"] = "subnet-public-1,subnet-public-2"
        os.environ["ECS_SECURITY_GROUP_IDS"] = "sg-sync"
        os.environ["ECS_ASSIGN_PUBLIC_IP"] = "ENABLED"

    @patch("sync_dispatcher.boto3.client")
    def test_dispatches_fargate_task_with_public_ip(self, boto_client: MagicMock) -> None:
        ecs_client = MagicMock()
        boto_client.return_value = ecs_client
        ecs_client.run_task.return_value = {"tasks": [{"taskArn": "arn:aws:ecs:task/1"}]}
        ecs_client.describe_tasks.return_value = {
            "tasks": [{"containers": [{"exitCode": 0}]}]
        }
        waiter = MagicMock()
        ecs_client.get_waiter.return_value = waiter

        event = {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "tenant": {"account": "acct", "project": "proj"},
                            "repo_url": "https://github.com/org/repo.git",
                            "after_sha": "abc123",
                        }
                    )
                }
            ]
        }

        result = sync_dispatcher.handler(event, None)
        self.assertEqual(result["status"], "ok")
        ecs_client.run_task.assert_called_once()
        network = ecs_client.run_task.call_args.kwargs["networkConfiguration"]["awsvpcConfiguration"]
        self.assertEqual(network["assignPublicIp"], "ENABLED")
        self.assertEqual(network["subnets"], ["subnet-public-1", "subnet-public-2"])
        overrides = ecs_client.run_task.call_args.kwargs["overrides"]["containerOverrides"][0]
        self.assertEqual(overrides["environment"][0]["name"], "SYNC_JOB_JSON")
        waiter.wait.assert_called_once()
        waiter_config = waiter.wait.call_args.kwargs["WaiterConfig"]
        self.assertEqual(waiter_config["Delay"], sync_dispatcher.TASK_STOP_WAITER_DELAY_SECONDS)
        self.assertGreaterEqual(
            waiter_config["Delay"] * waiter_config["MaxAttempts"],
            sync_dispatcher.DISPATCHER_TIMEOUT_SECONDS,
        )

    def test_task_stop_waiter_config_matches_dispatcher_timeout(self) -> None:
        os.environ["SYNC_TASK_STOP_WAIT_SECONDS"] = str(sync_dispatcher.DISPATCHER_TIMEOUT_SECONDS)
        waiter_config = sync_dispatcher._task_stop_waiter_config()
        self.assertGreaterEqual(
            waiter_config["Delay"] * waiter_config["MaxAttempts"],
            sync_dispatcher.DISPATCHER_TIMEOUT_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
