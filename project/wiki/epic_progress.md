# Epic progress

{% set epic = issue("tsk-epic01") %}
## {{ epic.title }}
{{ count(parent=epic.id, status="closed") }}/{{ count(parent=epic.id) }} tasks complete
