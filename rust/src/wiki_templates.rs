//! Default wiki page content for new projects.

pub const DEFAULT_WIKI_INDEX_FILENAME: &str = "index.md";
pub const DEFAULT_WIKI_WHATS_NEXT_FILENAME: &str = "whats-next.md";

pub const DEFAULT_WIKI_INDEX: &str = r#"# Project Wiki

Welcome to the project wiki.

## What's Next

See [What's Next](whats-next.md) for a report of upcoming work.
"#;

pub const DEFAULT_WIKI_WHATS_NEXT: &str = r#"# What's Next

Open issues, ordered by priority:

{% for issue in query(status="open", sort="priority") %}
- [{{ issue.title }}]({{ issue.id }})
{% endfor %}

{% if count(status="open") == 0 %}
No open issues.
{% endif %}
"#;
