"""Steps covering pytest migration scenarios."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import reload

from behave import then, when
from pydantic import ValidationError

from kanbus.models import DependencyLink, IssueComment, IssueData


@when("I import the kanbusr shim")
def when_import_kanbusr_shim(context: object) -> None:
    import kanbus
    import kanbusr

    context.kanbus_module = kanbus
    context.kanbusr_module = reload(kanbusr)


@then("the kanbusr version should match kanbus")
def then_kanbusr_version_matches(context: object) -> None:
    assert context.kanbusr_module.__version__ == context.kanbus_module.__version__


@then('the kanbusr shim should expose "__all__"')
def then_kanbusr_exposes_all(context: object) -> None:
    assert hasattr(context.kanbusr_module, "__all__")


@when('I build a sample issue with dependency "{target}" and comment author "{author}"')
def when_build_sample_issue(context: object, target: str, author: str) -> None:
    now = datetime.now(timezone.utc)
    context.sample_issue = IssueData(
        id="tsk-1",
        title="Test",
        description="",
        type="task",
        status="open",
        priority=1,
        assignee=None,
        creator=None,
        parent=None,
        labels=[],
        dependencies=[DependencyLink(target=target, type="blocked-by")],
        comments=[IssueComment(id="c1", author=author, text="hi", created_at=now)],
        created_at=now,
        updated_at=now,
        closed_at=None,
        custom={},
    )


@then('the issue identifier should be "{identifier}"')
def then_issue_identifier_matches(context: object, identifier: str) -> None:
    assert context.sample_issue.identifier == identifier


@then('the dependency type should be "{dependency_type}"')
def then_dependency_type_matches(context: object, dependency_type: str) -> None:
    assert context.sample_issue.dependencies[0].dependency_type == dependency_type


@then('the comment author should be "{author}"')
def then_comment_author_matches(context: object, author: str) -> None:
    assert context.sample_issue.comments[0].author == author


@when("I build a dependency link with empty type")
def when_build_dependency_link_empty_type(context: object) -> None:
    try:
        DependencyLink(target="tsk-1", type="")
        context.dependency_error = None
    except ValidationError as error:
        context.dependency_error = error


@then("the dependency link should fail validation")
def then_dependency_link_fails(context: object) -> None:
    assert context.dependency_error is not None
