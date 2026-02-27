"""Step definitions for policy feature tests."""

from __future__ import annotations

from behave import given


@given('a policy file "{filename}" with content')
def step_create_policy_file(context, filename: str) -> None:
    """Create a policy file with the given content."""
    policies_dir = context.project_dir / "policies"
    policies_dir.mkdir(exist_ok=True)
    policy_path = policies_dir / filename
    policy_path.write_text(context.text, encoding="utf-8")


@given("no policies directory exists")
def step_no_policies_directory(context) -> None:
    """Ensure no policies directory exists."""
    policies_dir = context.project_dir / "policies"
    if policies_dir.exists():
        import shutil

        shutil.rmtree(policies_dir)


@given("an empty policies directory exists")
def step_empty_policies_directory(context) -> None:
    """Create an empty policies directory."""
    policies_dir = context.project_dir / "policies"
    policies_dir.mkdir(exist_ok=True)
    for policy_file in policies_dir.glob("*.policy"):
        policy_file.unlink()
