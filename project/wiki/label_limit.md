# Label filter with limit

{% for issue in query(label="backend", status="open", limit=5, sort="-updated_at") %}
- [{{ issue.id }}] {{ issue.title }}
{% endfor %}
