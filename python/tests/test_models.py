from datetime import datetime, timezone

import pytest

from kanbus.models import IssueData, DependencyLink, IssueComment


def test_issue_data_valid():
    now = datetime.now(timezone.utc)
    issue = IssueData(
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
        dependencies=[DependencyLink(target="tsk-0", type="blocked-by")],
        comments=[
            IssueComment(id="c1", author="me", text="hi", created_at=now),
        ],
        created_at=now,
        updated_at=now,
        closed_at=None,
        custom={},
    )
    assert issue.identifier == "tsk-1"
    assert issue.dependencies[0].dependency_type == "blocked-by"
    assert issue.comments[0].author == "me"


def test_dependency_requires_type():
    with pytest.raises(Exception):
        DependencyLink(target="tsk-1", type="")
