# Issues by assignee

{% for issue in query(assignee="you@example.com", status="open") %}
- [{{ issue.id }}] {{ issue.title }}
{% endfor %}
