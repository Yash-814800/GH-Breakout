{#
  Shannon entropy in bits of a list of count expressions (NULL when the total is 0). Used for the
  event-type mix of a repo window.
#}
{% macro shannon_entropy_bits(exprs) %}
  {%- set total = '(' ~ exprs | join(' + ') ~ ')::double' -%}
  (case when {{ total }} > 0 then 0.0 - (
    {%- for e in exprs %}
      case when {{ e }} > 0 then ({{ e }}::double / {{ total }}) * log2({{ e }}::double / {{ total }}) else 0.0 end{{ ' +' if not loop.last }}
    {%- endfor %}
  ) end)
{% endmacro %}
