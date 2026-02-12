# Open tasks by priority

{% for issue in query(type="task", status="open", sort="priority") %}
- [{{ issue.id }}] {{ issue.title }} (P{{ issue.priority }})
{% endfor %}
