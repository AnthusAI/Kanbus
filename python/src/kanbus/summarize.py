"""Issue summarization using LiteLLM."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from kanbus.config_loader import load_project_configuration
from kanbus.issue_files import write_issue_to_file
from kanbus.issue_lookup import load_issue_from_project
from kanbus.models import IssueComment
from kanbus.project import get_configuration_path

try:
    import litellm
except ImportError:
    litellm = None


def compaction_summarize(root: Path, identifier: str, dry_run: bool = False) -> None:
    print(f"DEBUG cwd: {Path.cwd()}")

    """Summarize an issue using LiteLLM.

    :param root: Project root directory.
    :type root: Path
    :param identifier: Issue ID.
    :type identifier: str
    """
    config_path = get_configuration_path(root)
    config = load_project_configuration(config_path)

    if not config.ai or config.ai.provider != "litellm":
        raise RuntimeError("AI provider 'litellm' is not configured in .kanbus.yml")

    lookup = load_issue_from_project(root, identifier)
    issue = lookup.issue

    total_tokens = 0
    total_cost = 0.0

    # Determine mode
    is_archived = False
    if issue.status in ("closed", "done", "backlog"):
        age = datetime.now(timezone.utc) - issue.updated_at
        if age.days >= 30:
            is_archived = True

    issue_context = (
        f"Title: {issue.title}\n" f"Description: {issue.description}\n" f"Comments:\n"
    )
    for c in issue.comments:
        if getattr(c, "comment_type", "default") != "summary":
            issue_context += f"[{c.author}]: {c.text}\n"

    is_mock = os.environ.get("KANBUS_TEST_AI_MOCK") == "1"

    if is_mock:
        if is_archived:
            llm_summary = "### Results\nMock results.\n\n### Impact\nMock impact."
        else:
            llm_summary = (
                "### Current State\nMock state.\n\n### Action Items\nMock action items."
            )
        total_tokens = 42
        total_cost = 0.001
    else:
        if litellm is None:
            raise RuntimeError("litellm package is not installed")

        messages = [
            {
                "role": "system",
                "content": "You are a highly efficient coding agent assistant analyzing project issues.",
            }
        ]

        if is_archived:
            prompt = (
                f"Please analyze this closed/archived issue:\n\n{issue_context}\n\n"
                "Focus on the high-level Results and Impact. "
                "Output a markdown block with two sections: '### Results' (what was actually done or fixed) "
                "and '### Impact' (how this affects the system). "
                "Do NOT include day-to-day discussion details."
            )
        else:
            prompt = (
                f"Please analyze this active issue:\n\n{issue_context}\n\n"
                "Output a markdown block with the following sections:\n"
                "1. '### Current State' (brief summary of where things stand, synthesizing the noisy description and comments)\n"
                "2. '### Action Items' (bulleted list of pending tasks or unresolved questions)\n"
                "3. '### Key Artifacts' (bulleted list of important files, configs, or variables mentioned)\n"
                "4. '### Behavior Specification' (ONLY include this section if the original description contains a formal behavior specification like Gherkin 'Feature:', 'Scenario:', 'Given', 'When', 'Then'. If found, you MUST preserve it verbatim here)."
            )

        messages.append({"role": "user", "content": prompt})

        response = litellm.completion(model=config.ai.model, messages=messages)
        llm_summary = response.choices[0].message.content
        if hasattr(response, "usage") and response.usage:
            total_tokens += getattr(response.usage, "total_tokens", 0)

        try:
            cost = litellm.completion_cost(completion_response=response)
            if cost:
                total_cost += cost
        except Exception:
            pass

    # Programmatic Metadata Chunk
    metadata_chunk = (
        "### Issue Metadata\n"
        f"- **ID**: `{issue.identifier}`\n"
        f"- **Type**: `{issue.issue_type}`\n"
        f"- **Status**: `{issue.status}`\n"
        f"- **Created**: `{issue.created_at.strftime('%Y-%m-%d')}`\n"
        f"- **Updated**: `{issue.updated_at.strftime('%Y-%m-%d')}`\n"
        f"- **Mode**: `{'Archived' if is_archived else 'Active'}`\n"
    )

    final_summary = f"{metadata_chunk}\n{llm_summary}"

    events_dir = root / config.project_directory / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    log_path = events_dir / "llm_usage.jsonl"
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "issue_id": issue.identifier,
        "model": config.ai.model,
        "tokens": total_tokens,
        "cost": total_cost,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    if dry_run:
        print(f"Summary for {issue.identifier} (dry-run):")
        print("--------------------------------------------------")
        print(final_summary)
        print("--------------------------------------------------")
        return

    comment = IssueComment(
        id=str(uuid.uuid4()),
        author="system:summary",
        text=final_summary,
        created_at=datetime.now(timezone.utc),
        comment_type="summary",
    )
    issue.comments.append(comment)
    issue.updated_at = datetime.now(timezone.utc)
    write_issue_to_file(issue, lookup.issue_path)
    print(f"Summary saved for {issue.identifier}")
