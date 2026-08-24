"""Issue summarization using LiteLLM."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from kanbus.config_loader import load_project_configuration
from kanbus.issue_files import write_issue_to_file
from kanbus.issue_listing import load_issues_from_directory
from kanbus.issue_lookup import load_issue_from_project
from kanbus.models import IssueComment
from kanbus.project import get_configuration_path

try:
    import litellm
except ImportError:
    litellm = None


def _append_issue_context(
    issue_context: str,
    issue: object,
    all_issues: list,
) -> str:
    if getattr(issue, "parent", None):
        parent_issue = next(
            (
                candidate
                for candidate in all_issues
                if candidate.identifier == issue.parent
            ),
            None,
        )
        if parent_issue is not None:
            if (
                parent_issue.comments
                and getattr(parent_issue.comments[-1], "comment_type", "default")
                == "summary"
            ):
                parent_summary = parent_issue.comments[-1].text
            else:
                parent_summary = parent_issue.description
            issue_context = (
                f"\n[PARENT CONTEXT: {issue.parent}]\n{parent_summary}\n\n"
                + issue_context
            )

    dependencies = getattr(issue, "dependencies", None)
    if dependencies:
        dependencies_context = "\n[DEPENDENCIES CONTEXT]\n"
        for dependency in dependencies:
            dependency_issue = next(
                (
                    candidate
                    for candidate in all_issues
                    if candidate.identifier == dependency.target
                ),
                None,
            )
            if dependency_issue is None:
                continue
            if (
                dependency_issue.comments
                and getattr(dependency_issue.comments[-1], "comment_type", "default")
                == "summary"
            ):
                dependency_summary = dependency_issue.comments[-1].text
            else:
                dependency_summary = dependency_issue.description
            dependencies_context += (
                f"Dependency ({dependency.dependency_type} {dependency.target}):\n"
                f"{dependency_summary}\n\n"
            )
        issue_context = dependencies_context + issue_context

    return issue_context


def _append_child_context(
    root: Path,
    identifier: str,
    issue_context: str,
    all_issues: list,
    dry_run: bool,
) -> str:
    child_issues = [issue for issue in all_issues if issue.parent == identifier]
    if not child_issues:
        return issue_context

    issue_context += "\nDescendant Issues State:\n"
    for child in child_issues:
        child_summary_text = None
        if (
            child.comments
            and getattr(child.comments[-1], "comment_type", "default") == "summary"
        ):
            child_summary_text = child.comments[-1].text
        elif dry_run:
            issue_context += f"- {child.identifier}: [Would be summarized]\n"
            continue
        else:
            child_summary_text = compaction_summarize(
                root, child.identifier, dry_run=False
            )

        if child_summary_text:
            match = re.search(
                r"(### (?:Rewritten Description|Activity Summary).*?)(?=\n### |$)",
                child_summary_text,
                re.DOTALL,
            )
            extracted = match.group(1).strip() if match else child_summary_text.strip()
            issue_context += f"--- Child {child.identifier} ---\n{extracted}\n\n"

    return issue_context


def _record_llm_usage(
    root: Path,
    project_directory: str,
    issue_identifier: str,
    model: str,
    total_tokens: int,
    total_cost: float,
) -> None:
    events_dir = root / project_directory / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    log_path = events_dir / "llm_usage.jsonl"
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "issue_id": issue_identifier,
        "model": model,
        "tokens": total_tokens,
        "cost": total_cost,
    }
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(log_entry) + "\n")


def compaction_summarize(
    root: Path, identifier: str, dry_run: bool = False
) -> str | None:
    """Summarize an issue using LiteLLM.

    :param root: Project root directory.
    :type root: Path
    :param identifier: Issue ID.
    :type identifier: str
    :param dry_run: Print the summary without saving when set.
    :type dry_run: bool
    :return: Generated summary text, or None for dry-run without persistence.
    :rtype: str | None
    """
    config_path = get_configuration_path(root)
    config = load_project_configuration(config_path)

    if not config.ai or config.ai.provider != "litellm":
        raise RuntimeError("AI provider 'litellm' is not configured in .kanbus.yml")

    lookup = load_issue_from_project(root, identifier)
    issue = lookup.issue

    total_tokens = 0
    total_cost = 0.0

    issue_context = (
        f"Title: {issue.title}\nDescription: {issue.description}\nComments:\n"
    )
    for comment in issue.comments:
        if getattr(comment, "comment_type", "default") != "summary":
            issue_context += f"[{comment.author}]: {comment.text}\n"

    issues_dir = root / config.project_directory / "issues"
    all_issues = load_issues_from_directory(issues_dir)
    issue_context = _append_issue_context(issue_context, issue, all_issues)
    issue_context = _append_child_context(
        root, identifier, issue_context, all_issues, dry_run
    )

    is_mock = os.environ.get("KANBUS_TEST_AI_MOCK") == "1"

    if is_mock:
        llm_summary = (
            "### Rewritten Description\n"
            "Mock rewritten description.\n\n"
            "### Activity Summary\n"
            "Mock activity summary."
        )
        total_tokens = 42
        total_cost = 0.001
    else:
        if litellm is None:
            raise RuntimeError("litellm package is not installed")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a highly efficient coding agent assistant "
                    "analyzing project issues."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Please analyze this issue:\n\n{issue_context}\n\n"
                    "You are an expert technical writer. You must rewrite the "
                    "description holistically by incorporating the context from "
                    "parents, children, and dependencies. "
                    "Output exactly two sections:\n"
                    "'### Rewritten Description' (The holistic rewrite of the "
                    "issue's purpose and scope)\n"
                    "'### Activity Summary' (The compacted history of progress "
                    "and decisions)\n"
                    "Do NOT output anything else. Do NOT duplicate metadata "
                    "like status or timestamps."
                ),
            },
        ]

        if dry_run:
            print(f"Summary for {issue.identifier} (dry-run):")
            print("--------------------------------------------------")
            print(messages[1]["content"])
            print("--------------------------------------------------")
            return None

        response = litellm.completion(model=config.ai.model, messages=messages)
        llm_summary = response.choices[0].message.content or ""
        if hasattr(response, "usage") and response.usage:
            total_tokens += getattr(response.usage, "total_tokens", 0)

        try:
            cost = litellm.completion_cost(completion_response=response)
            if cost:
                total_cost += cost
        except Exception:
            pass

    llm_summary = llm_summary.replace("```markdown\n", "").replace("\n```", "").strip()

    _record_llm_usage(
        root,
        config.project_directory,
        issue.identifier,
        config.ai.model,
        total_tokens,
        total_cost,
    )

    if dry_run:
        print(f"Summary for {issue.identifier} (dry-run):")
        print("--------------------------------------------------")
        print(llm_summary)
        print("--------------------------------------------------")
        return None

    summary_comment = IssueComment(
        id=str(uuid.uuid4()),
        author="system:summary",
        text=llm_summary,
        created_at=datetime.now(timezone.utc),
        comment_type="summary",
    )
    issue.comments = [
        comment
        for comment in issue.comments
        if getattr(comment, "comment_type", "default") != "summary"
    ]
    issue.comments.append(summary_comment)
    issue.updated_at = datetime.now(timezone.utc)
    write_issue_to_file(issue, lookup.issue_path)
    print(f"Summary saved for {issue.identifier}")
    return llm_summary
