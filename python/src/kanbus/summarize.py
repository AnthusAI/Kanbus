"""Issue summarization using LiteLLM."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from kanbus.comment_summary import (
    SUMMARY_ACTIVITY_SUMMARY_KEY,
    SUMMARY_REWRITTEN_DESCRIPTION_KEY,
    get_comment_display_text,
    get_latest_summary_comment,
    get_summary_activity_summary,
    get_summary_rewritten_description,
    get_virtualized_description,
)
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

COMPACTION_PROFILE_ACTIVE = "active"
COMPACTION_PROFILE_RECENT_CLOSED = "recent_closed"
COMPACTION_PROFILE_ARCHIVED = "archived"
COMPACTION_PROFILE_DEEP_ARCHIVE = "deep_archive"

CLOSED_STATUSES = frozenset({"closed", "done"})

DESCRIPTION_PROFILE_GUIDANCE = {
    COMPACTION_PROFILE_ACTIVE: (
        4,
        "Write 2-4 short sentences. State the goal clearly. Improve accuracy and brevity.",
    ),
    COMPACTION_PROFILE_RECENT_CLOSED: (
        3,
        "Write 1-3 short sentences focused on the outcome.",
    ),
    COMPACTION_PROFILE_ARCHIVED: (
        2,
        "Write at most 2 short sentences. Headline-level summary only.",
    ),
    COMPACTION_PROFILE_DEEP_ARCHIVE: (
        1,
        "Write a single short sentence with the bare minimum context.",
    ),
}

DESCRIPTION_LENGTH_RATIOS = {
    COMPACTION_PROFILE_ACTIVE: 0.85,
    COMPACTION_PROFILE_RECENT_CLOSED: 0.65,
    COMPACTION_PROFILE_ARCHIVED: 0.45,
    COMPACTION_PROFILE_DEEP_ARCHIVE: 0.30,
}

DESCRIPTION_LENGTH_FLOORS = {
    COMPACTION_PROFILE_ACTIVE: 80,
    COMPACTION_PROFILE_RECENT_CLOSED: 60,
    COMPACTION_PROFILE_ARCHIVED: 40,
    COMPACTION_PROFILE_DEEP_ARCHIVE: 25,
}


def resolve_compaction_profile(issue: object) -> str:
    """Resolve the compaction profile for an issue.

    :param issue: Issue data object.
    :type issue: object
    :return: Compaction profile name.
    :rtype: str
    """
    status = getattr(issue, "status", "open")
    updated_at = getattr(issue, "updated_at", None)
    age_days = 0
    if isinstance(updated_at, datetime):
        age_days = (datetime.now(timezone.utc) - updated_at).days

    if status in CLOSED_STATUSES or status == "backlog":
        if age_days >= 90:
            return COMPACTION_PROFILE_DEEP_ARCHIVE
        if age_days >= 30:
            return COMPACTION_PROFILE_ARCHIVED
        return COMPACTION_PROFILE_RECENT_CLOSED
    return COMPACTION_PROFILE_ACTIVE


def _description_character_budget(
    original_description: str, profile: str
) -> int | None:
    """Return the maximum allowed rewritten description length.

    :param original_description: Original issue description text.
    :type original_description: str
    :param profile: Compaction profile name.
    :type profile: str
    :return: Character budget when the original description is non-empty.
    :rtype: int | None
    """
    original_length = len(original_description.strip())
    if original_length == 0:
        return None
    ratio = DESCRIPTION_LENGTH_RATIOS.get(profile, 0.85)
    floor = DESCRIPTION_LENGTH_FLOORS.get(profile, 80)
    return max(floor, int(original_length * ratio))


def build_summary_comment(
    rewritten_description: str,
    activity_summary: str,
) -> IssueComment:
    """Create a structured compaction summary comment.

    :param rewritten_description: LLM rewritten issue description.
    :type rewritten_description: str
    :param activity_summary: LLM activity summary.
    :type activity_summary: str
    :return: Summary comment with structured data fields.
    :rtype: IssueComment
    """
    return IssueComment(
        id=str(uuid.uuid4()),
        author="system:summary",
        created_at=datetime.now(timezone.utc),
        comment_type="summary",
        data={
            SUMMARY_REWRITTEN_DESCRIPTION_KEY: rewritten_description,
            SUMMARY_ACTIVITY_SUMMARY_KEY: activity_summary,
        },
    )


def _find_issue(all_issues: list, identifier: str) -> object | None:
    return next(
        (candidate for candidate in all_issues if candidate.identifier == identifier),
        None,
    )


def _build_description_context(issue: object, all_issues: list, profile: str) -> str:
    """Build prompt context for rewritten description generation.

    :param issue: Issue being summarized.
    :type issue: object
    :param all_issues: All issues in the project.
    :type all_issues: list
    :param profile: Compaction profile name.
    :type profile: str
    :return: Description-only prompt context.
    :rtype: str
    """
    max_sentences, profile_guidance = DESCRIPTION_PROFILE_GUIDANCE[profile]
    context_lines = [
        f"Title: {issue.title}",
        f"Type: {getattr(issue, 'issue_type', 'task')}",
        f"Status: {getattr(issue, 'status', 'open')}",
        f"Compaction profile: {profile}",
        f"Original Description:\n{issue.description}",
    ]

    parent_identifier = getattr(issue, "parent", None)
    if parent_identifier:
        parent_issue = _find_issue(all_issues, parent_identifier)
        if parent_issue is not None:
            parent_goal = (
                get_virtualized_description(parent_issue).strip().splitlines()[0]
            )
            context_lines.append(f"Parent goal ({parent_identifier}): {parent_goal}")

    existing_summary = get_latest_summary_comment(issue)
    if existing_summary is not None:
        previous_rewritten = get_summary_rewritten_description(existing_summary)
        if previous_rewritten:
            context_lines.append(
                "Previous rewritten description to compress further:\n"
                f"{previous_rewritten}"
            )

    context_lines.append(
        "Description rewrite constraints:\n"
        f"- {profile_guidance}\n"
        f"- Use at most {max_sentences} sentence(s).\n"
        "- State what the issue is trying to accomplish.\n"
        "- Do not include progress, status, task lists, repository names, "
        "decisions, blockers, or details from comments.\n"
        "- Be shorter than the original description unless the original is empty."
    )
    return "\n\n".join(context_lines)


def _build_comment_context(issue: object) -> str:
    comment_lines = []
    for comment in issue.comments:
        if getattr(comment, "comment_type", "default") != "summary":
            comment_lines.append(
                f"[{comment.author}]: {get_comment_display_text(comment)}"
            )
    if not comment_lines:
        return "(no comments)"
    return "\n".join(comment_lines)


def _append_child_activity_context(
    root: Path,
    identifier: str,
    activity_context: str,
    all_issues: list,
    dry_run: bool,
) -> str:
    child_issues = [issue for issue in all_issues if issue.parent == identifier]
    if not child_issues:
        return activity_context

    activity_context += "\n\nDescendant Issues:\n"
    for child in child_issues:
        child_summary = get_latest_summary_comment(child)
        if child_summary is not None:
            child_activity = get_summary_activity_summary(child_summary)
        elif dry_run:
            activity_context += (
                f"- {child.identifier} ({child.status}): [Would be summarized]\n"
            )
            continue
        else:
            compaction_summarize(root, child.identifier, dry_run=False)
            refreshed = load_issue_from_project(root, child.identifier).issue
            refreshed_summary = get_latest_summary_comment(refreshed)
            child_activity = ""
            if refreshed_summary is not None:
                child_activity = get_summary_activity_summary(refreshed_summary)
        activity_context += (
            f"- {child.identifier} ({child.status}): "
            f"{get_virtualized_description(child)}\n"
            f"  Activity: {child_activity or '(none)'}\n"
        )

    return activity_context


def _append_dependency_activity_context(
    activity_context: str,
    issue: object,
    all_issues: list,
) -> str:
    dependencies = getattr(issue, "dependencies", None)
    if not dependencies:
        return activity_context

    activity_context += "\n\nDependency Activity:\n"
    for dependency in dependencies:
        dependency_issue = _find_issue(all_issues, dependency.target)
        if dependency_issue is None:
            continue
        dependency_summary = get_latest_summary_comment(dependency_issue)
        dependency_activity = ""
        if dependency_summary is not None:
            dependency_activity = get_summary_activity_summary(dependency_summary)
        activity_context += (
            f"- {dependency.dependency_type} {dependency.target}: "
            f"{dependency_activity or '(none)'}\n"
        )
    return activity_context


def _build_activity_context(
    issue: object,
    all_issues: list,
    root: Path,
    identifier: str,
    dry_run: bool,
) -> str:
    """Build prompt context for activity summary generation.

    :param issue: Issue being summarized.
    :type issue: object
    :param all_issues: All issues in the project.
    :type all_issues: list
    :param root: Project root directory.
    :type root: Path
    :param identifier: Issue identifier.
    :type identifier: str
    :param dry_run: Whether this is a dry-run invocation.
    :type dry_run: bool
    :return: Activity-only prompt context.
    :rtype: str
    """
    activity_context = f"Comments:\n{_build_comment_context(issue)}"
    activity_context = _append_child_activity_context(
        root, identifier, activity_context, all_issues, dry_run
    )
    activity_context = _append_dependency_activity_context(
        activity_context, issue, all_issues
    )
    return activity_context


def _record_llm_usage(
    root: Path,
    project_directory: str,
    issue_identifier: str,
    model: str,
    operation: str,
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
        "operation": operation,
        "tokens": total_tokens,
        "cost": total_cost,
    }
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(log_entry) + "\n")


def _completion(
    model: str,
    messages: list[dict[str, str]],
    issue_identifier: str,
    operation: str,
    root: Path,
    project_directory: str,
    temperature: float | None = None,
) -> str:
    if os.environ.get("KANBUS_TEST_AI_MOCK") == "1":
        if operation == "compaction_rewritten_description":
            text = f"Mock rewritten description for {issue_identifier}."
        elif operation == "compaction_rewritten_description_retry":
            text = f"Mock rewritten description for {issue_identifier}."
        else:
            text = f"Mock activity summary for {issue_identifier}."
        _record_llm_usage(
            root, project_directory, issue_identifier, model, operation, 21, 0.0005
        )
        return text

    if litellm is None:
        raise RuntimeError("litellm package is not installed")

    completion_kwargs: dict[str, object] = {"model": model, "messages": messages}
    if temperature is not None:
        completion_kwargs["temperature"] = temperature

    response = litellm.completion(**completion_kwargs)
    text = response.choices[0].message.content or ""
    total_tokens = 0
    total_cost = 0.0
    if hasattr(response, "usage") and response.usage:
        total_tokens += getattr(response.usage, "total_tokens", 0)
    try:
        cost = litellm.completion_cost(completion_response=response)
        if cost:
            total_cost += cost
    except Exception:
        pass

    _record_llm_usage(
        root,
        project_directory,
        issue_identifier,
        model,
        operation,
        total_tokens,
        total_cost,
    )
    return text.strip()


def _generate_rewritten_description(
    description_context: str,
    profile: str,
    model: str,
    issue_identifier: str,
    root: Path,
    project_directory: str,
    *,
    retry_because_too_long: bool = False,
    character_budget: int | None = None,
    previous_attempt: str | None = None,
) -> str:
    retry_instruction = ""
    if retry_because_too_long and previous_attempt and character_budget is not None:
        retry_instruction = (
            f"\n\nYour previous rewrite was too long ({len(previous_attempt)} characters). "
            f"The maximum allowed length is {character_budget} characters. "
            "Cut it roughly in half. Remove examples, lists, and implementation detail."
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You rewrite Kanbus issue descriptions to be accurate, brief, and high-level. "
                "Descriptions state the goal of the issue, not its history."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{description_context}{retry_instruction}\n\n"
                "Rewrite the issue description.\n"
                "Return only the rewritten description as plain markdown prose.\n"
                "Do not include headings, labels, metadata, bullet lists, code blocks, "
                "or an activity summary."
            ),
        },
    ]
    operation = (
        "compaction_rewritten_description_retry"
        if retry_because_too_long
        else "compaction_rewritten_description"
    )
    return _completion(
        model,
        messages,
        issue_identifier,
        operation,
        root,
        project_directory,
    )


def _generate_activity_summary(
    rewritten_description: str,
    activity_context: str,
    profile: str,
    model: str,
    issue_identifier: str,
    root: Path,
    project_directory: str,
) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You write Kanbus activity summaries that capture what has happened on an issue."
            ),
        },
        {
            "role": "user",
            "content": (
                "Issue goal:\n"
                f"{rewritten_description}\n\n"
                "Summarize activity for this issue using only the material below.\n"
                "Include concrete progress, findings, decisions, blockers, child-task status, "
                "repository names, and open questions when present.\n"
                "Do not restate the issue goal.\n"
                "Return only the activity summary as plain markdown prose.\n\n"
                f"{activity_context}"
            ),
        },
    ]
    return _completion(
        model,
        messages,
        issue_identifier,
        "compaction_activity_summary",
        root,
        project_directory,
    )


def _rewrite_description_with_guardrails(
    description_context: str,
    profile: str,
    original_description: str,
    model: str,
    issue_identifier: str,
    root: Path,
    project_directory: str,
) -> str:
    character_budget = _description_character_budget(original_description, profile)
    rewritten_description = _generate_rewritten_description(
        description_context,
        profile,
        model,
        issue_identifier,
        root,
        project_directory,
    )
    if (
        character_budget is not None
        and len(rewritten_description) > character_budget
        and original_description.strip()
    ):
        rewritten_description = _generate_rewritten_description(
            description_context,
            profile,
            model,
            issue_identifier,
            root,
            project_directory,
            retry_because_too_long=True,
            character_budget=character_budget,
            previous_attempt=rewritten_description,
        )
    return rewritten_description


def apply_virtualized_issue_view(issue: object, raw: bool) -> object:
    """Apply compaction virtualization rules for display.

    :param issue: Issue data to virtualize in place.
    :type issue: object
    :param raw: Whether to show the uncompacted view.
    :type raw: bool
    :return: The same issue object for chaining.
    :rtype: object
    """
    summary_comment = get_latest_summary_comment(issue)
    if summary_comment is None:
        return issue

    if raw:
        return issue

    rewritten_description = get_summary_rewritten_description(summary_comment)
    if rewritten_description is not None:
        issue.description = rewritten_description

    virtualized_comments = [summary_comment]
    for comment in issue.comments:
        if comment.created_at > summary_comment.created_at:
            virtualized_comments.append(comment)
    issue.comments = virtualized_comments
    return issue


def compaction_summarize(
    root: Path, identifier: str, dry_run: bool = False
) -> str | None:
    """Summarize an issue using two sequential LiteLLM calls.

    :param root: Project root directory.
    :type root: Path
    :param identifier: Issue ID.
    :type identifier: str
    :param dry_run: Print prompts without saving when set.
    :type dry_run: bool
    :return: Rewritten description text, or None for dry-run without persistence.
    :rtype: str | None
    """
    config_path = get_configuration_path(root)
    config = load_project_configuration(config_path)

    if not config.ai or config.ai.provider != "litellm":
        raise RuntimeError("AI provider 'litellm' is not configured in .kanbus.yml")

    lookup = load_issue_from_project(root, identifier)
    issue = lookup.issue
    original_description = issue.description
    profile = resolve_compaction_profile(issue)

    issues_dir = root / config.project_directory / "issues"
    all_issues = load_issues_from_directory(issues_dir)
    description_context = _build_description_context(issue, all_issues, profile)
    activity_context = _build_activity_context(
        issue, all_issues, root, identifier, dry_run
    )

    if dry_run:
        print(f"Summary for {issue.identifier} (dry-run, profile={profile}):")
        print("--------------------------------------------------")
        print("Rewritten description context:")
        print(description_context)
        print("--------------------------------------------------")
        print("Activity summary context:")
        print(activity_context)
        print("--------------------------------------------------")
        return None

    rewritten_description = _rewrite_description_with_guardrails(
        description_context,
        profile,
        original_description,
        config.ai.model,
        issue.identifier,
        root,
        config.project_directory,
    )
    activity_summary = _generate_activity_summary(
        rewritten_description,
        activity_context,
        profile,
        config.ai.model,
        issue.identifier,
        root,
        config.project_directory,
    )

    issue.comments.append(
        build_summary_comment(rewritten_description, activity_summary)
    )
    issue.updated_at = datetime.now(timezone.utc)
    write_issue_to_file(issue, lookup.issue_path)
    print(f"Summary saved for {issue.identifier}")
    return rewritten_description
