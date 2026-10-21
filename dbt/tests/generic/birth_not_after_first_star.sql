{% test birth_not_after_first_star(model, tolerance=0.001) %}
{#
  A repo cannot be born after its first star (the API created_at may be up to a day late, so one
  day of slack). Fails only when more than `tolerance` (a share) of repos violate it, and always
  logs the count; below the tolerance it reports nothing.
#}
{% set q %}
    select count(*) filter (where birth_at > first_star_at + interval 1 day) as n_bad, count(*) as n_all
    from {{ model }} where first_star_at is not null and not is_left_censored
{% endset %}
{# the count is only logged when tests run; docs generate and compile have no data #}
{% if execute and flags.WHICH in ('test', 'build') %}
  {% set r = run_query(q).rows[0] %}
  {{ log('birth_not_after_first_star: ' ~ r[0] ~ ' of ' ~ r[1] ~ ' repos violate it', info=True) }}
{% endif %}
select n_bad, n_all
from ({{ q }})
where n_bad > {{ tolerance }} * n_all
{% endtest %}
