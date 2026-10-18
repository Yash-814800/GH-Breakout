{% test monotonic_cumulative(model, partition_by, order_by, columns) %}
{# running totals must never decrease along order_by within a partition; returns violations #}
select *
from (
    select {{ partition_by }}, {{ order_by }},
    {% for c in columns %}
        {{ c }} < lag({{ c }}) over w as dec_{{ loop.index }}{{ ',' if not loop.last }}
    {% endfor %}
    from {{ model }}
    window w as (partition by {{ partition_by }} order by {{ order_by }})
)
where {% for c in columns %}coalesce(dec_{{ loop.index }}, false){{ ' or ' if not loop.last }}{% endfor %}
{% endtest %}
