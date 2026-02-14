# Wiki Guide

Kanbus wiki pages are Markdown files with Jinja2-style templates. At render time, Kanbus evaluates the template against the live issue index and outputs a fully rendered Markdown document.

## Where wiki pages live

Wiki pages live in `project/wiki/`. Use `kanbus wiki render <page>` to render a page and print the result to stdout.

## Jinja2 primer

- `{{ expr }}` renders an expression
- `{% for x in items %}` loops over a list
- `{% if condition %}` controls conditional output
- `{# comment #}` is a template comment

Example:

```markdown
{% if count(status="open") == 0 %}
All clear.
{% else %}
Open issues: {{ count(status="open") }}
{% endif %}
```

## Template functions

The following functions are available in all wiki templates:

- `query(**filters)` -> list of issues
- `count(**filters)` -> integer
- `issue(id)` -> issue or None
- `children(id)` -> list of issues
- `blocked_by(id)` -> list of issues
- `blocks(id)` -> list of issues

Common filters for `query` and `count`:

- `type` (exact match)
- `status` (exact match)
- `priority` (exact match)
- `priority_lte` / `priority_gte`
- `assignee`
- `label`
- `parent`
- `sort` (prefix with `-` for descending)
- `limit`

## Examples

### 1) Basic status counts

```markdown
Open: {{ count(status="open") }}
Closed: {{ count(status="closed") }}
```

### 2) List open tasks by priority

```markdown
{% for issue in query(type="task", status="open", sort="priority") %}
- [{{ issue.id }}] {{ issue.title }} (P{{ issue.priority }})
{% endfor %}
```

### 3) Epic progress summary

```markdown
{% set epic = issue("kanbus-epic01") %}
## {{ epic.title }}
{{ count(parent=epic.id, status="closed") }}/{{ count(parent=epic.id) }} tasks complete
```

### 4) Show blocked issues with blockers

```markdown
{% for issue in query(status="blocked") %}
- [{{ issue.id }}] {{ issue.title }}
  Blocked by:
  {% for blocker in blocked_by(issue.id) %}
  - [{{ blocker.id }}] {{ blocker.title }}
  {% endfor %}
{% endfor %}
```

### 5) Issues by assignee

```markdown
{% for issue in query(assignee="you@example.com", status="open") %}
- [{{ issue.id }}] {{ issue.title }}
{% endfor %}
```

### 6) High-priority work queue

```markdown
{% for issue in query(status="open", priority_lte=1, sort="priority") %}
- [{{ issue.id }}] {{ issue.title }} (P{{ issue.priority }})
{% endfor %}
```

### 7) Status summary table

```markdown
| Status | Count |
|--------|-------|
| Open | {{ count(status="open") }} |
| In progress | {{ count(status="in_progress") }} |
| Blocked | {{ count(status="blocked") }} |
| Closed | {{ count(status="closed") }} |
```

### 8) Single issue detail block

```markdown
{% set item = issue("kanbus-a1b2c3") %}
## {{ item.title }}
Status: {{ item.status }}
Priority: {{ item.priority }}
Assignee: {{ item.assignee or "unassigned" }}
```

### 9) Show children of an epic

```markdown
{% for child in children("kanbus-epic01") %}
- [{{ child.id }}] {{ child.title }} ({{ child.status }})
{% endfor %}
```

### 10) Show what an issue blocks

```markdown
{% for blocked in blocks("kanbus-epic01") %}
- [{{ blocked.id }}] {{ blocked.title }}
{% endfor %}
```

### 11) Filter by label with limit

```markdown
{% for issue in query(label="backend", status="open", limit=5, sort="-updated_at") %}
- [{{ issue.id }}] {{ issue.title }}
{% endfor %}
```

## Rendering

Render a wiki page from the project root:

```bash
kanbus wiki render project/wiki/index.md
```

For more CLI details, see [CLI_REFERENCE.md](CLI_REFERENCE.md).
