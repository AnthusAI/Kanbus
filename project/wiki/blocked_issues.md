# Blocked issues

{% for issue in query(status="blocked") %}
- [{{ issue.id }}] {{ issue.title }}
  Blocked by:
  {% for blocker in blocked_by(issue.id) %}
  - [{{ blocker.id }}] {{ blocker.title }}
  {% endfor %}
{% endfor %}
