#!/usr/bin/env python3
"""Run the explicit real AWS test against the known isolated fixture only."""

import json
import os
import subprocess
from pathlib import Path

PROFILE = "cyclotron-production"
ACCOUNT = "682849160744"
STACK = "virtuus-store-proof-20261014-aws01"
REGION = "us-east-1"


def aws(*args):
    """Read AWS CLI JSON without printing credentials."""
    return json.loads(
        subprocess.check_output(
            ["aws", "--profile", PROFILE, "--region", REGION, *args]
        )
    )


def main():
    """Guard account and fixture ownership, then run ignored integration proof."""
    identity = aws("sts", "get-caller-identity")
    if identity["Account"] != ACCOUNT:
        raise SystemExit("Wrong AWS account; refusing to run")
    stack = aws("cloudformation", "describe-stacks", "--stack-name", STACK)["Stacks"][0]
    if stack["StackStatus"] != "CREATE_COMPLETE":
        raise SystemExit("Fixture stack must be CREATE_COMPLETE")
    outputs = {item["OutputKey"]: item["OutputValue"] for item in stack["Outputs"]}
    credentials = aws("configure", "export-credentials", "--format", "process")
    environment = os.environ.copy()
    environment.update(
        {
            "AWS_ACCESS_KEY_ID": credentials["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": credentials["SecretAccessKey"],
            "AWS_SESSION_TOKEN": credentials["SessionToken"],
            "VIRTUUS_TEST_BUCKET": outputs["Bucket"],
            "VIRTUUS_TEST_TABLE": outputs["Table"],
            "VIRTUUS_TEST_REGION": REGION,
            "AWS_REGION": REGION,
            "RUSTUP_TOOLCHAIN": "stable",
            "CARGO_INCREMENTAL": "0",
            "CARGO_BUILD_JOBS": "2",
            "PATH": str(Path.home() / ".cargo/bin") + os.pathsep + os.environ.get("PATH", ""),
            "VIRTUUS_TEST_RUN": os.environ.get(
                "VIRTUUS_TEST_RUN", f"proof-api-{os.getpid()}"
            ),
            "RUSTC": str(Path.home() / ".cargo/bin/rustc"),
            "RUSTDOC": str(Path.home() / ".cargo/bin/rustdoc"),
        }
    )
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            str(Path.home() / ".cargo/bin/cargo"),
            "test",
            "--locked",

            "--features",
            "aws",
            "--test",
            "aws_api",
            os.environ.get("VIRTUUS_TEST_FILTER", ""),
            "--",
            "--ignored",
            "--nocapture",
        ],
        cwd=root,
        env=environment,
        check=False,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
