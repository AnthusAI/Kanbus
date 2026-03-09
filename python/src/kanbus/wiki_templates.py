"""Default wiki page content for new projects."""

from __future__ import annotations

DEFAULT_WIKI_INDEX_FILENAME = "index.md"
DEFAULT_WIKI_WHATS_NEXT_FILENAME = "whats-next.md"

DEFAULT_WIKI_INDEX = """# Project Wiki

Welcome to the project wiki.

## What's Next

See [What's Next](whats-next.md) for a report of upcoming work.
"""

DEFAULT_WIKI_WHATS_NEXT = """# What's Next

Open issues, ordered by priority:

{% for issue in query(status="open", sort="priority") %}
- [{{ issue.title }}]({{ issue.id }})
{% endfor %}

{% if count(status="open") == 0 %}
No open issues.
{% endif %}
"""
