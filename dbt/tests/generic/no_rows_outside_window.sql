{% test no_rows_outside_window(model, column_name) %}
{# staging respects events_start (inclusive) and events_end (exclusive); returns offending rows #}
select {{ column_name }}
from {{ model }}
where {{ column_name }} < timestamp '{{ var("events_start") }}'
   or {{ column_name }} >= timestamp '{{ var("events_end") }}'
{% endtest %}
