# Issues blocked by an epic

{% for blocked in blocks("tsk-epic01") %}
- [{{ blocked.id }}] {{ blocked.title }}
{% endfor %}
