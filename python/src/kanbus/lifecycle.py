import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from kanbus.config_loader import load_project_configuration
from kanbus.project import get_configuration_path
from kanbus.summarize import compaction_summarize
from kanbus.issue_listing import load_issues_from_directory


def run_lifecycle_compaction(
    root: Path,
    all: bool = False,
    query: Optional[str] = None,
    dry_run: bool = False,
    archived_only: bool = False,
    max_items: Optional[int] = None,
) -> None:
    config_path = get_configuration_path(root)
    config = load_project_configuration(config_path)

    if not config.ai or config.ai.provider != "litellm":
        raise RuntimeError("AI provider 'litellm' is not configured in .kanbus.yml")

    issues_dir = root / config.project_directory / "issues"
    issues = load_issues_from_directory(issues_dir)

    eligible = []

    for issue in issues:
        # Check if already summarized
        if issue.comments and issue.comments[-1].comment_type == "summary":
            continue

        # Check archived only
        if archived_only:
            if issue.status not in ("closed", "done", "backlog"):
                continue
            age = datetime.now(timezone.utc) - issue.updated_at
            if age.days < 30:
                continue

        eligible.append(issue)

    if max_items is not None and max_items > 0:
        eligible = eligible[:max_items]

    if dry_run:
        print("Dry-run mode: no issues were modified.")
        for issue in eligible:
            print(f"Would summarize {issue.identifier}")
        return

    for issue in eligible:
        try:
            compaction_summarize(root, issue.identifier, dry_run=False)
        except SystemExit as exc:
            if getattr(exc, "code", 0) not in (0, None):
                raise
        print(f"Summary saved for {issue.identifier}")

    print(f"Processed {len(eligible)} issues")

    events_dir = root / config.project_directory / "events"
    log_path = events_dir / "llm_usage.jsonl"
    total_cost = 0.0

    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        total_cost += float(data.get("cost", 0.0))
                    except Exception:
                        pass

    print(f"Total cost: ${total_cost:.4f}")
