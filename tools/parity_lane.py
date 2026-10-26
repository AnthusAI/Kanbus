#!/usr/bin/env python3
"""
Run the same golden commands through the Rust kbs and the Python kanbus CLIs
and diff stdout, stderr, exit code and the resulting project files.

Both implementations are full, independent ports, so every observable
difference is a bug in one of them. Differences that exist today are listed
in tools/parity/known_divergences.txt; the lane fails on any difference that
is not listed and on any listed difference that has been fixed, so the list
only ever shrinks.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_COMMANDS_PATH = REPOSITORY_ROOT / "tools" / "parity" / "golden_commands.txt"
KNOWN_DIVERGENCES_PATH = REPOSITORY_ROOT / "tools" / "parity" / "known_divergences.txt"

TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
EVENT_FILE_PATTERN = re.compile(r"^(?P<directory>.*/events)/[^/]+__[^/]+\.json$")
COMMENT_IDENTIFIER_PATTERN = re.compile(r"\[[0-9a-f]{6}\]")
TEMPORARY_PATH_PATTERN = re.compile(r"/(?:private/)?(?:tmp|var/folders)/[^\s\"']+")
DEFAULT_COMMAND_TIMEOUT_SECONDS = 120
INIT_SCENARIO_NAME = "init"


@dataclass
class Scenario:
    name: str
    command_lines: List[str] = field(default_factory=list)


@dataclass
class StepOutcome:
    stdout: str
    stderr: str
    exit_code: int


def normalise_text(text: str, working_directory: Path) -> str:
    text = text.replace(str(working_directory), "<PROJECT>")
    text = TEMPORARY_PATH_PATTERN.sub("<TMP>", text)
    text = TIMESTAMP_PATTERN.sub("<TS>", text)
    text = COMMENT_IDENTIFIER_PATTERN.sub("[<COMMENT>]", text)
    return UUID_PATTERN.sub("<UUID>", text)


def sequence_event_files(files: Dict[str, str]) -> Dict[str, str]:
    events_by_directory: Dict[str, List[str]] = {}
    sequenced: Dict[str, str] = {}
    for relative, content in files.items():
        match = EVENT_FILE_PATTERN.match(relative)
        if match is None:
            sequenced[relative] = content
            continue
        events_by_directory.setdefault(match.group("directory"), []).append(content)
    for directory, contents in events_by_directory.items():
        for position, content in enumerate(sorted(contents), start=1):
            sequenced[f"{directory}/event-{position:04d}.json"] = content
    return sequenced


def parse_scenarios(path: Path) -> List[Scenario]:
    scenarios: List[Scenario] = []
    current: Optional[Scenario] = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or (line.startswith("#") and not line.startswith("# scenario:")):
            continue
        if line.startswith("# scenario:"):
            current = Scenario(name=line.split(":", 1)[1].strip())
            scenarios.append(current)
            continue
        if current is None:
            raise ValueError(f"command before first '# scenario:' header: {line}")
        current.command_lines.append(line)
    return scenarios


def prepare_environment(home_directory: Path) -> Dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("KANBUS_") and key not in ("OPENAI_API_KEY",)
    }
    environment.update(
        {
            "HOME": str(home_directory),
            "KANBUS_DAEMON": "0",
            "OPENAI_API_KEY": "parity-lane-placeholder",
            "NO_COLOR": "1",
            "GIT_AUTHOR_NAME": "parity",
            "GIT_AUTHOR_EMAIL": "parity@example.invalid",
            "GIT_COMMITTER_NAME": "parity",
            "GIT_COMMITTER_EMAIL": "parity@example.invalid",
        }
    )
    return environment


def snapshot_files(project_directory: Path) -> Dict[str, bytes]:
    files: Dict[str, bytes] = {}
    for path in sorted(project_directory.rglob("*")):
        relative = path.relative_to(project_directory)
        if ".git" in relative.parts or not path.is_file():
            continue
        files[relative.as_posix()] = path.read_bytes()
    return files


def run_scenario_with(
    executable: List[str], scenario: Scenario
) -> Tuple[List[StepOutcome], Dict[str, bytes], Dict[str, bytes], Path]:
    working_directory = Path(tempfile.mkdtemp(prefix="parity-lane-"))
    project_directory = working_directory / "project-root"
    home_directory = working_directory / "home"
    project_directory.mkdir()
    home_directory.mkdir()
    environment = prepare_environment(home_directory)
    subprocess.run(
        ["git", "init", "-q"], cwd=project_directory, env=environment, check=True
    )
    outcomes: List[StepOutcome] = []
    snapshot_after_init: Dict[str, bytes] = {}
    for index, command_line in enumerate(scenario.command_lines):
        completed = subprocess.run(
            executable + shlex.split(command_line),
            cwd=project_directory,
            env=environment,
            capture_output=True,
            text=True,
            timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        )
        outcomes.append(
            StepOutcome(
                normalise_text(completed.stdout, project_directory),
                normalise_text(completed.stderr, project_directory),
                completed.returncode,
            )
        )
        if index == 0:
            snapshot_after_init = snapshot_files(project_directory)
    final_files = snapshot_files(project_directory)
    return outcomes, snapshot_after_init, final_files, project_directory


def comparable_files(
    scenario: Scenario,
    after_init: Dict[str, bytes],
    final_files: Dict[str, bytes],
    project_directory: Path,
) -> Dict[str, str]:
    comparable: Dict[str, str] = {}
    for relative, content in final_files.items():
        if scenario.name != INIT_SCENARIO_NAME and after_init.get(relative) == content:
            continue
        text = normalise_text(
            content.decode("utf-8", errors="replace"), project_directory
        )
        comparable[relative] = text
    return sequence_event_files(comparable)


def describe_difference(left: str, right: str) -> str:
    left_lines = left.splitlines()
    right_lines = right.splitlines()
    for line_number in range(max(len(left_lines), len(right_lines))):
        left_line = left_lines[line_number] if line_number < len(left_lines) else "<missing>"
        right_line = right_lines[line_number] if line_number < len(right_lines) else "<missing>"
        if left_line != right_line:
            return f"line {line_number + 1}: rust={left_line[:160]!r} python={right_line[:160]!r}"
    return "identical"


def find_divergences(
    scenarios: List[Scenario], rust_command: List[str], python_command: List[str]
) -> Dict[str, str]:
    divergences: Dict[str, str] = {}
    for scenario in scenarios:
        rust_outcomes, rust_init, rust_files, rust_directory = run_scenario_with(
            rust_command, scenario
        )
        python_outcomes, python_init, python_files, python_directory = (
            run_scenario_with(python_command, scenario)
        )
        for index, (rust_outcome, python_outcome) in enumerate(
            zip(rust_outcomes, python_outcomes)
        ):
            step_label = f"{scenario.name}::{index + 1}"
            for field_name in ("stdout", "stderr"):
                rust_value = getattr(rust_outcome, field_name)
                python_value = getattr(python_outcome, field_name)
                if rust_value != python_value:
                    divergences[f"{step_label}::{field_name}"] = describe_difference(
                        rust_value, python_value
                    )
            if rust_outcome.exit_code != python_outcome.exit_code:
                divergences[f"{step_label}::exit"] = (
                    f"rust={rust_outcome.exit_code} python={python_outcome.exit_code}"
                )
        rust_comparable = comparable_files(scenario, rust_init, rust_files, rust_directory)
        python_comparable = comparable_files(
            scenario, python_init, python_files, python_directory
        )
        for relative in sorted(set(rust_comparable) | set(python_comparable)):
            rust_text = rust_comparable.get(relative)
            python_text = python_comparable.get(relative)
            if rust_text == python_text:
                continue
            key = f"{scenario.name}::file::{relative}"
            if rust_text is None:
                divergences[key] = "only in python"
            elif python_text is None:
                divergences[key] = "only in rust"
            else:
                divergences[key] = describe_difference(rust_text, python_text)
        for directory in (rust_directory.parent, python_directory.parent):
            shutil.rmtree(directory, ignore_errors=True)
    return divergences


def read_known_divergences(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def write_known_divergences(path: Path, keys: Set[str]) -> None:
    header = (
        "# Observable differences between kbs (Rust) and kanbus (Python) that exist\n"
        "# today. Fix the implementation, then delete the line. The parity lane fails\n"
        "# on new differences and on lines here that no longer differ.\n"
    )
    path.write_text(header + "\n".join(sorted(keys)) + "\n", encoding="utf-8")


def resolve_executable(command: List[str]) -> List[str]:
    if "/" in command[0]:
        resolved = str(Path(command[0]).resolve())
    else:
        resolved = shutil.which(command[0]) or command[0]
    return [resolved] + command[1:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rust", required=True, help="path to the kbs binary")
    parser.add_argument(
        "--python",
        required=True,
        help="path to the kanbus executable (or 'python -m kanbus')",
    )
    parser.add_argument("--scenarios", type=Path, default=GOLDEN_COMMANDS_PATH)
    parser.add_argument("--known", type=Path, default=KNOWN_DIVERGENCES_PATH)
    parser.add_argument(
        "--update-known",
        action="store_true",
        help="rewrite the known-divergences file from the current state",
    )
    parser.add_argument("--only", help="run only the scenario with this name")
    arguments = parser.parse_args()

    rust_command = resolve_executable(shlex.split(arguments.rust))
    python_command = resolve_executable(shlex.split(arguments.python))
    scenarios = parse_scenarios(arguments.scenarios)
    if arguments.only:
        scenarios = [s for s in scenarios if s.name == arguments.only]
    divergences = find_divergences(scenarios, rust_command, python_command)

    if arguments.update_known:
        write_known_divergences(arguments.known, set(divergences))
        print(f"wrote {len(divergences)} known divergences to {arguments.known}")
        return 0

    known = read_known_divergences(arguments.known)
    run_scenario_names = {scenario.name for scenario in scenarios}
    known_in_scope = {
        key for key in known if key.split("::", 1)[0] in run_scenario_names
    }
    new_divergences = sorted(set(divergences) - known)
    fixed_divergences = sorted(known_in_scope - set(divergences))

    for key in new_divergences:
        print(f"NEW DIVERGENCE {key}: {divergences[key]}")
    for key in fixed_divergences:
        print(f"FIXED, remove from known_divergences.txt: {key}")
    print(
        f"parity lane: {len(scenarios)} scenarios, {len(divergences)} divergences "
        f"({len(known_in_scope)} known, {len(new_divergences)} new, "
        f"{len(fixed_divergences)} fixed)"
    )
    return 1 if new_divergences or fixed_divergences else 0


if __name__ == "__main__":
    sys.exit(main())
