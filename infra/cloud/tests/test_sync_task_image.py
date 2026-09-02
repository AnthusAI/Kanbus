"""Validate sync task container dependencies."""

import unittest
from pathlib import Path


class SyncTaskImageDependencyTests(unittest.TestCase):
    """Ensure Fargate sync image declares runtime dependencies."""

    @staticmethod
    def _requirements_path() -> Path:
        return Path(__file__).resolve().parents[1] / "lambda" / "requirements.txt"

    def test_requirements_include_boto3(self) -> None:
        requirements = self._requirements_path().read_text(encoding="utf-8")
        self.assertIn("boto3", requirements)

    def test_sync_worker_imports_boto3_module(self) -> None:
        import importlib.util

        worker_path = Path(__file__).resolve().parents[1] / "lambda" / "sync_worker.py"
        spec = importlib.util.spec_from_file_location("sync_worker_under_test", worker_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(hasattr(module, "process_job"))


if __name__ == "__main__":
    unittest.main()
