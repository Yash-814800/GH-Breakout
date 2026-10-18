{#
  Exactly-once file list for a lake table.

  The lake guarantees one row per event_id across the files of a month, except for locally kept
  Phase 1 test days (`day-*.parquet` next to a `month-*`/`bq-*` file of the same month). Those day
  files are dropped here, so staging never needs a global dedupe sort over billions of rows.
  Only files of the years the events window touches (or an explicit year range) are listed.
#}
{% macro lake_glob(kind) %}
  {%- if kind == 'push_daily' -%}
    {{ return(env_var('GHB_LAKE') ~ '/push_daily/**/*.parquet') }}
  {%- else -%}
    {{ return(env_var('GHB_LAKE') ~ '/events/event_type=' ~ kind ~ '/**/*.parquet') }}
  {%- endif -%}
{% endmacro %}

{% macro lake_file_list(kind, year_from=none, year_to=none) %}
  {%- set pattern = lake_glob(kind) -%}
  {%- set yrs = window_years() -%}
  {%- set y_lo = year_from if year_from is not none else yrs | first -%}
  {%- set y_hi = year_to if year_to is not none else yrs | last -%}
  {%- if not execute -%}
    {{ return([pattern]) }}
  {%- endif -%}
  {%- set q -%}
    with f as (select file as path, regexp_replace(file, '/[^/]+$', '') as dir,
                      regexp_extract(file, '/([^/]+)$', 1) as base
               from glob('{{ pattern }}')
               where try_cast(regexp_extract(file, 'year=([0-9]+)', 1) as integer)
                     between {{ y_lo }} and {{ y_hi }}),
    full_months as (select distinct dir from f where base not like 'day-%')
    select path from f
    where base not like 'day-%' or dir not in (select dir from full_months)
    order by path
  {%- endset -%}
  {{ return(run_query(q).columns[0].values()) }}
{% endmacro %}

{% macro lake_events(kind, year_from=none, year_to=none) %}
  {%- set files = lake_file_list(kind, year_from, year_to) -%}
  {%- if files | length == 0 -%}
    {#- no file in the range (e.g. reviews before 2020): empty relation with the right schema -#}
    {%- set any_file = run_query("select min(file) from glob('" ~ lake_glob(kind) ~ "')").columns[0].values()[0] -%}
    (select * from read_parquet('{{ any_file }}', hive_partitioning = false) where false)
  {%- else -%}
    read_parquet([{% for p in files %}'{{ p | replace("'", "''") }}'{{ ', ' if not loop.last }}{% endfor %}],
                 hive_partitioning = false, union_by_name = true)
  {%- endif -%}
{% endmacro %}
