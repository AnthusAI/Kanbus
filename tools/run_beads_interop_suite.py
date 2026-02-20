#!/usr/bin/env python3
"""Run Beads interoperability checks across Kanbus Python and Rust CLIs."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    """Result of a subprocess command."""

    command: list[str]
    cwd: Path | None
    return_code: int
    stdout: str
    stderr: str


def run_command(
    command: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> CommandResult:
    """Run a subprocess command and capture output.

    :param command: Command and arguments to execute.
    :type command: list[str]
    :param cwd: Working directory for the command.
    :type cwd: Path | None
    :param env: Optional environment overrides.
    :type env: dict[str, str] | None
    :return: Command result with stdout/stderr and return code.
    :rtype: CommandResult
    """
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return CommandResult(
        command=command,
        cwd=cwd,
        return_code=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )

def _format_command(result: CommandResult) -> str:
    return " ".join(result.command)


def _format_result(result: CommandResult, label: str) -> str:
    parts = [
        f"{label} failed",
        f"command: {_format_command(result)}",
        f"cwd: {result.cwd or os.getcwd()}",
        f"exit code: {result.return_code}",
    ]
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if stdout:
        parts.append("stdout:")
        parts.append(stdout)
    else:
        parts.append("stdout: <empty>")
    if stderr:
        parts.append("stderr:")
        parts.append(stderr)
    else:
        parts.append("stderr: <empty>")
    return "\n".join(parts)


def ensure_success(result: CommandResult, label: str) -> None:
    """Ensure the command succeeded or raise an error.

    :param result: Command result.
    :type result: CommandResult
    :param label: Human-readable label for the command.
    :type label: str
    :raises RuntimeError: If the command failed.
    """
    if result.return_code != 0:
        raise RuntimeError(_format_result(result, label))


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text.

    :param text: Input text.
    :type text: str
    :return: Cleaned text.
    :rtype: str
    """
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def parse_json_payload(text: str, label: str) -> object:
    """Parse JSON payload from command output that may include warnings.

    :param text: Command stdout text.
    :type text: str
    :param label: Label for error reporting.
    :type label: str
    :return: Parsed JSON payload.
    :rtype: object
    :raises RuntimeError: If no JSON payload can be parsed.
    """
    cleaned = text.lstrip()
    brace_index = cleaned.find("{")
    bracket_index = cleaned.find("[")
    candidates = [idx for idx in (brace_index, bracket_index) if idx != -1]
    if not candidates:
        raise RuntimeError(f"{label} returned no JSON payload")
    start_index = min(candidates)
    payload_text = cleaned[start_index:]
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{label} returned invalid JSON: {error}\nRaw payload:\n{payload_text}"
        ) from error


def parse_json_payload_from_streams(
    stdout: str, stderr: str, label: str
) -> object:
    """Parse JSON payload from stdout or stderr.

    :param stdout: Standard output.
    :type stdout: str
    :param stderr: Standard error.
    :type stderr: str
    :param label: Label for error reporting.
    :type label: str
    :return: Parsed JSON payload.
    :rtype: object
    """
    try:
        return parse_json_payload(stdout, label)
    except RuntimeError as error:
        if "no JSON payload" in str(error) and stderr.strip():
            return parse_json_payload(stderr, label)
        raise


def load_beads_records(issues_path: Path) -> list[dict]:
    """Load Beads JSONL records.

    :param issues_path: Path to the issues.jsonl file.
    :type issues_path: Path
    :return: Parsed records.
    :rtype: list[dict]
    """
    records: list[dict] = []
    for line in issues_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def parse_kanbus_identifier(output: str) -> str:
    """Extract a Kanbus or Beads identifier from CLI output.

    :param output: CLI output text.
    :type output: str
    :return: Extracted issue identifier.
    :rtype: str
    :raises RuntimeError: If no identifier is found.
    """
    cleaned = strip_ansi(output)
    match = re.search(r"([A-Za-z]+-[A-Za-z0-9.]+)", cleaned)
    if match is None:
        raise RuntimeError("unable to locate issue identifier in output")
    return match.group(1)


def ensure_issues_jsonl(beads_dir: Path) -> None:
    """Ensure .beads/issues.jsonl exists, seeding from issues.jsonl.new if needed.

    :param beads_dir: Path to the .beads directory.
    :type beads_dir: Path
    :raises RuntimeError: If no issues file is available.
    """
    issues_path = beads_dir / "issues.jsonl"
    if issues_path.exists():
        return
    seeded = beads_dir / "issues.jsonl.new"
    if seeded.exists():
        shutil.copyfile(seeded, issues_path)
        return
    raise RuntimeError("no issues.jsonl available in Beads repository")


def write_beads_config(beads_dir: Path) -> None:
    """Write a config.yaml forcing JSONL and no-daemon mode.

    :param beads_dir: Path to the .beads directory.
    :type beads_dir: Path
    """
    config_path = beads_dir / "config.yaml"
    config_path.write_text("no-db: true\nno-daemon: true\n", encoding="utf-8")


def clone_beads_repo(
    source: str, branch: str | None, destination: Path
) -> CommandResult:
    """Clone the Beads repository.

    :param source: Git URL or local path.
    :type source: str
    :param branch: Optional branch or tag.
    :type branch: str | None
    :param destination: Destination directory.
    :type destination: Path
    :return: Command result from git clone.
    :rtype: CommandResult
    """
    command = ["git", "clone", "--depth", "1"]
    if branch:
        command.extend(["-b", branch])
    command.extend([source, str(destination)])
    return run_command(command)


def build_beads_cli(beads_repo: Path, output_dir: Path) -> Path:
    """Build the Beads CLI from the cloned repository.

    :param beads_repo: Path to the cloned Beads repository.
    :type beads_repo: Path
    :param output_dir: Directory for the built binary.
    :type output_dir: Path
    :return: Path to the bd binary.
    :rtype: Path
    :raises RuntimeError: If the build fails or binary is missing.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    suppress_beads_test_helpers(beads_repo)
    binary = output_dir / "bd"
    result = run_command(["go", "build", "-o", str(binary), "./cmd/bd"], cwd=beads_repo)
    ensure_success(result, "bd build")
    if not binary.exists():
        raise RuntimeError("bd binary not found after build")
    return binary


def suppress_beads_test_helpers(beads_repo: Path) -> None:
    """Disable Beads test-only helpers that break `go build` in CI."""
    helper = beads_repo / "cmd" / "bd" / "test_wait_helper.go"
    if helper.exists():
        helper.rename(helper.with_suffix(".go.disabled"))


def run_beads_list(
    bd_binary: Path, repo_root: Path, env: dict[str, str]
) -> list[dict]:
    """Run bd list --json and parse results.

    :param bd_binary: Path to the bd binary.
    :type bd_binary: Path
    :param repo_root: Beads repository root.
    :type repo_root: Path
    :param env: Environment variables.
    :type env: dict[str, str]
    :return: Parsed list output.
    :rtype: list[dict]
    """
    result = run_command(
        [
            str(bd_binary),
            "list",
            "--json",
            "--all",
        ],
        cwd=repo_root,
        env=env,
    )
    ensure_success(result, "bd list")
    payload = parse_json_payload_from_streams(result.stdout, result.stderr, "bd list")
    if not isinstance(payload, list):
        raise RuntimeError("bd list returned unexpected JSON")
    return payload


def find_issue_in_list(list_payload: list[dict], identifier: str) -> dict | None:
    """Find an issue by id in bd list output.

    :param list_payload: Parsed bd list output.
    :type list_payload: list[dict]
    :param identifier: Issue identifier to search for.
    :type identifier: str
    :return: Matching issue payload or None.
    :rtype: dict | None
    """
    for item in list_payload:
        if item.get("id") == identifier:
            return item
    return None


def find_issue_by_title(
    records: list[dict], title: str, parent_id: str | None
) -> dict | None:
    """Find an issue by title in Beads JSONL records.

    :param records: Beads JSONL records.
    :type records: list[dict]
    :param title: Issue title to match.
    :type title: str
    :param parent_id: Optional parent id to match in dependencies.
    :type parent_id: str | None
    :return: Matching issue record or None.
    :rtype: dict | None
    """
    for record in reversed(records):
        if record.get("title") != title:
            continue
        if parent_id is None:
            return record
        dependencies = record.get("dependencies") or []
        for dependency in dependencies:
            if (
                isinstance(dependency, dict)
                and dependency.get("type") == "parent-child"
                and dependency.get("depends_on_id") == parent_id
            ):
                return record
    return None


def run_kanbus_python(
    python_executable: Path, args: list[str], cwd: Path, env: dict[str, str]
) -> CommandResult:
    """Run the Kanbus Python CLI.

    :param python_executable: Path to the Python interpreter.
    :type python_executable: Path
    :param args: CLI arguments for kanbus.cli.
    :type args: list[str]
    :param cwd: Working directory for the command.
    :type cwd: Path
    :param env: Environment variables.
    :type env: dict[str, str]
    :return: Command result.
    :rtype: CommandResult
    """
    command = [str(python_executable), "-m", "kanbus.cli", *args]
    return run_command(command, cwd=cwd, env=env)


def run_kanbus_rust(
    rust_binary: Path, args: list[str], cwd: Path, env: dict[str, str]
) -> CommandResult:
    """Run the Kanbus Rust CLI.

    :param rust_binary: Path to the Rust CLI binary.
    :type rust_binary: Path
    :param args: CLI arguments.
    :type args: list[str]
    :param cwd: Working directory for the command.
    :type cwd: Path
    :param env: Environment variables.
    :type env: dict[str, str]
    :return: Command result.
    :rtype: CommandResult
    """
    command = [str(rust_binary), *args]
    return run_command(command, cwd=cwd, env=env)


def parse_kanbus_json(result: CommandResult, label: str) -> dict:
    """Parse JSON output from Kanbus show --json.

    :param result: Command result.
    :type result: CommandResult
    :param label: Label for error messages.
    :type label: str
    :return: Parsed JSON payload.
    :rtype: dict
    """
    ensure_success(result, label)
    payload = parse_json_payload_from_streams(result.stdout, result.stderr, label)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} returned unexpected JSON")
    return payload


def select_jsonl_issue_id(records: list[dict]) -> str:
    """Select a Beads issue without parent-child dependencies.

    :param records: Beads JSONL records.
    :type records: list[dict]
    :return: Selected issue id.
    :rtype: str
    :raises RuntimeError: If no suitable issue is found.
    """
    for record in records:
        identifier = record.get("id")
        if not identifier:
            continue
        dependencies = record.get("dependencies") or []
        parent_links = [
            dep
            for dep in dependencies
            if isinstance(dep, dict) and dep.get("type") == "parent-child"
        ]
        if not parent_links:
            return str(identifier)
    raise RuntimeError("no suitable Beads issue found for interoperability checks")


def main(argv: list[str]) -> int:
    """Run interoperability checks.

    :param argv: Command-line arguments.
    :type argv: list[str]
    :return: Exit code.
    :rtype: int
    """
    parser = argparse.ArgumentParser(description="Run Beads interoperability suite")
    parser.add_argument(
        "--beads-source",
        default="https://github.com/steveyegge/beads",
        help="Git URL or local path to the Beads repository.",
    )
    parser.add_argument(
        "--beads-branch",
        default="v0.50.3",
        help="Optional Beads branch or tag to clone.",
    )
    parser.add_argument(
        "--python",
        default=None,
        help="Python interpreter to use for Kanbus CLI.",
    )
    parser.add_argument(
        "--bd-binary",
        default=None,
        help="Path to an existing bd binary (skips building from source).",
    )
    parser.add_argument(
        "--rust-binary",
        default=None,
        help="Path to the Kanbus Rust CLI binary.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    python_executable = Path(args.python) if args.python else Path(sys.executable)
    rust_binary = (
        Path(args.rust_binary)
        if args.rust_binary
        else repo_root / "rust" / "target" / "release" / "kbs"
    )

    if not rust_binary.exists():
        print("rust binary not found; build it before running the suite")
        return 1

    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["KANBUS_NO_DAEMON"] = "1"

    try:
        with tempfile.TemporaryDirectory(prefix="kanbus-beads-interop-") as temp_dir:
            workspace = Path(temp_dir)
            beads_repo = workspace / "beads_repo"
            clone_result = clone_beads_repo(
                args.beads_source, args.beads_branch, beads_repo
            )
            ensure_success(clone_result, "clone Beads repository")

            beads_dir = beads_repo / ".beads"
            ensure_issues_jsonl(beads_dir)
            write_beads_config(beads_dir)

            if args.bd_binary:
                bd_binary = Path(args.bd_binary)
                if not bd_binary.exists():
                    raise RuntimeError("bd binary not found")
            else:
                bd_binary = build_beads_cli(beads_repo, workspace / "bin")

            records = load_beads_records(beads_dir / "issues.jsonl")
            existing_issue_id = select_jsonl_issue_id(records)
            list_payload = run_beads_list(bd_binary, beads_repo, env)
            list_ids = {item.get("id") for item in list_payload if item.get("id")}
            if existing_issue_id not in list_ids:
                raise RuntimeError("selected Beads issue not found in bd list output")

            python_show = run_kanbus_python(
                python_executable,
                ["--beads", "show", existing_issue_id, "--json"],
                cwd=beads_repo,
                env=env,
            )
            python_payload = parse_kanbus_json(python_show, "kanbus python show")
            if python_payload.get("id") != existing_issue_id:
                raise RuntimeError("python CLI failed to read existing Beads issue")

            rust_show = run_kanbus_rust(
                rust_binary,
                ["--beads", "show", existing_issue_id, "--json"],
                cwd=beads_repo,
                env=env,
            )
            rust_payload = parse_kanbus_json(rust_show, "kanbus rust show")
            if rust_payload.get("id") != existing_issue_id:
                raise RuntimeError("rust CLI failed to read existing Beads issue")

            beads_create = run_command(
                [
                    str(bd_binary),
                    "--quiet",
                    "create",
                    "Interop epic from beads",
                    "--type",
                    "epic",
                    "--json",
                ],
                cwd=beads_repo,
                env=env,
            )
            ensure_success(beads_create, "bd create")
            beads_created = parse_json_payload_from_streams(
                beads_create.stdout, beads_create.stderr, "bd create"
            )
            beads_created_id = beads_created.get("id")
            if not beads_created_id:
                raise RuntimeError("bd create did not return an id")

            python_show_created = run_kanbus_python(
                python_executable,
                ["--beads", "show", beads_created_id, "--json"],
                cwd=beads_repo,
                env=env,
            )
            python_created_payload = parse_kanbus_json(
                python_show_created, "kanbus python show beads created"
            )
            if python_created_payload.get("id") != beads_created_id:
                raise RuntimeError("python CLI failed to read Beads-created issue")

            rust_show_created = run_kanbus_rust(
                rust_binary,
                ["--beads", "show", beads_created_id, "--json"],
                cwd=beads_repo,
                env=env,
            )
            rust_created_payload = parse_kanbus_json(
                rust_show_created, "kanbus rust show beads created"
            )
            if rust_created_payload.get("id") != beads_created_id:
                raise RuntimeError("rust CLI failed to read Beads-created issue")

            python_child_title = "Interop child from python"
            python_create = run_kanbus_python(
                python_executable,
                [
                    "--beads",
                    "create",
                    python_child_title,
                    "--parent",
                    beads_created_id,
                ],
                cwd=beads_repo,
                env=env,
            )
            ensure_success(python_create, "kanbus python create")
            records_after_python = load_beads_records(beads_dir / "issues.jsonl")
            python_child_record = find_issue_by_title(
                records_after_python, python_child_title, beads_created_id
            )
            if python_child_record is None:
                raise RuntimeError("Kanbus Python did not write Beads JSONL record")
            python_child_id = str(python_child_record.get("id"))

            list_after_python = run_beads_list(bd_binary, beads_repo, env)
            beads_child = find_issue_in_list(list_after_python, python_child_id)
            if beads_child is None:
                raise RuntimeError("Beads CLI failed to list Kanbus-created issue")
            dependencies = beads_child.get("dependencies") or []
            parent_links = [
                dep
                for dep in dependencies
                if isinstance(dep, dict)
                and dep.get("type") == "parent-child"
                and dep.get("depends_on_id") == beads_created_id
            ]
            if not parent_links:
                raise RuntimeError("Beads CLI did not report expected parent")

            rust_update = run_kanbus_rust(
                rust_binary,
                ["--beads", "update", python_child_id, "--status", "closed"],
                cwd=beads_repo,
                env=env,
            )
            ensure_success(rust_update, "kanbus rust update")
            list_after_update = run_beads_list(bd_binary, beads_repo, env)
            beads_child_updated = find_issue_in_list(
                list_after_update, python_child_id
            )
            if beads_child_updated is None:
                raise RuntimeError("Beads CLI failed to list updated issue")
            if beads_child_updated.get("status") != "closed":
                raise RuntimeError("Beads CLI did not report updated status")

            rust_delete = run_kanbus_rust(
                rust_binary,
                ["--beads", "delete", python_child_id],
                cwd=beads_repo,
                env=env,
            )
            ensure_success(rust_delete, "kanbus rust delete")
            list_after = run_beads_list(bd_binary, beads_repo, env)
            list_after_ids = {item.get("id") for item in list_after}
            if python_child_id in list_after_ids:
                raise RuntimeError("Beads CLI still lists deleted issue")
    except RuntimeError as error:
        print(str(error))
        return 1

    print("Beads interoperability suite succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
