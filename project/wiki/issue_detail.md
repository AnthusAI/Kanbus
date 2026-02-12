# Issue detail

{% set item = issue("tsk-a1b2c3") %}
## {{ item.title }}
Status: {{ item.status }}
Priority: {{ item.priority }}
Assignee: {{ item.assignee or "unassigned" }}
