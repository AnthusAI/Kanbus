# High priority queue

{% for issue in query(status="open", priority_lte=1, sort="priority") %}
- [{{ issue.id }}] {{ issue.title }} (P{{ issue.priority }})
{% endfor %}
