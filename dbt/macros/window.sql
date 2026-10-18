{# created_at window for staging: events_start inclusive, events_end exclusive (UTC, naive) #}
{% macro window_filter(col='created_at') %}
  {{ col }} >= timestamp '{{ var("events_start") }}' and {{ col }} < timestamp '{{ var("events_end") }}'
{% endmacro %}

{# years touched by the events window, as a list of ints #}
{% macro window_years() %}
  {%- set y0 = var('events_start')|string %}
  {%- set y1 = var('events_end')|string %}
  {%- set a = y0[:4]|int %}
  {%- set b = y1[:4]|int %}
  {%- if y1[5:10] == '01-01' %}{% set b = b - 1 %}{% endif %}
  {{ return(range(a, b + 1)) }}
{% endmacro %}

{# [(month_start, next_month_start, year)] for every month the events window touches, as ISO strings #}
{% macro window_months() %}
  {%- set a = var('events_start')|string %}
  {%- set b = var('events_end')|string %}
  {%- set ns = namespace(y=a[:4]|int, m=a[5:7]|int, out=[]) %}
  {%- for _ in range(0, 1400) %}
    {%- set cur = '%04d-%02d-01' | format(ns.y, ns.m) %}
    {%- if cur < b %}
      {%- set ny = ns.y + (1 if ns.m == 12 else 0) %}
      {%- set nm = 1 if ns.m == 12 else ns.m + 1 %}
      {%- set _ = ns.out.append((cur, '%04d-%02d-01' | format(ny, nm), ns.y)) %}
      {%- set ns.y = ny %}{% set ns.m = nm %}
    {%- endif %}
  {%- endfor %}
  {{ return(ns.out) }}
{% endmacro %}

{#
  Bucketed builds (ADR-020). The biggest tables (all stars, per-repo star days, per-actor activity)
  do not fit in the memory cap in one statement, so they are built one hash bucket of a key per dbt
  call. `bucket` (var) selects the bucket, unset = all buckets in one go (small windows, daily run).
  Every bucketed model is incremental with unique_key = bucket (delete + insert).
#}
{% macro bucket_col(col, n=none) %}(({{ col }}) % {{ n if n is not none else var('n_buckets', 32) }})::smallint{% endmacro %}

{% macro bucket_filter(col, n=none) %}
  {%- if var('bucket', none) is not none -%}
    ({{ col }}) % {{ n if n is not none else var('n_buckets', 32) }} = {{ var('bucket') }}
  {%- else -%}
    true
  {%- endif -%}
{% endmacro %}
