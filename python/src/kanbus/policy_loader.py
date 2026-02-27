"""Policy file loading and parsing."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from gherkin.parser import Parser
from types import SimpleNamespace

if TYPE_CHECKING:
    from gherkin.ast import GherkinDocument


class PolicyLoadError(RuntimeError):
    """Raised when policy loading fails."""


def load_policies(policies_dir: Path) -> list[tuple[str, GherkinDocument]]:
    """Load and parse all .policy files from the policies directory.

    :param policies_dir: Path to the policies directory.
    :type policies_dir: Path
    :return: List of tuples containing filename and parsed Gherkin document.
    :rtype: list[tuple[str, GherkinDocument]]
    :raises PolicyLoadError: If parsing fails.
    """
    if not policies_dir.exists() or not policies_dir.is_dir():
        return []

    parser = Parser()
    documents = []

    for policy_file in policies_dir.glob("*.policy"):
        try:
            content = policy_file.read_text(encoding="utf-8")
            document = parser.parse(content)
            documents.append((policy_file.name, _to_namespace(document)))
        except Exception as error:
            message = f"failed to parse {policy_file.name}: {error}"
            raise PolicyLoadError(message) from error

    return documents


def _to_namespace(node: object) -> object:
    """Recursively convert dictionaries returned by gherkin into attribute objects."""

    if isinstance(node, dict):
        return SimpleNamespace(
            **{key: _to_namespace(value) for key, value in node.items()}
        )
    if isinstance(node, list):
        return [_to_namespace(value) for value in node]
    return node
