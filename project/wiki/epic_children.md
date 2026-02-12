# Epic children

{% for child in children("tsk-epic01") %}
- [{{ child.id }}] {{ child.title }} ({{ child.status }})
{% endfor %}
