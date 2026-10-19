{{ config(materialized='incremental', unique_key=['bucket', 'snapshot_date'], incremental_strategy='delete+insert', on_schema_change='fail') }}
{#
  Grain (repo_id, snapshot_date): THE model input. mart_candidates (keys only) LEFT JOIN every feature group.
  Same SQL for the weekly history and for live scoring (snapshot_dates_mode = single). Columns starting with
  an underscore (_max_input_ts of each group) are test-only and are not in the mart. Built per repo_id bucket.
  `bucket` is a build key, not a feature. Every other column is in config/feature_dictionary.yaml.
#}
select
    c.bucket, c.repo_id, c.snapshot_date,
    {% for g in ['star_dynamics', 'activity', 'stargazers', 'tastemaker', 'owner', 'detail', 'enrich'] %}
    {{ dbt_utils.star(ref('feat_' ~ g), relation_alias='g_' ~ g, except=['bucket', 'repo_id', 'snapshot_date', '_max_input_ts']) }}{{ ',' if not loop.last }}
    {% endfor %}
from {{ ref('mart_candidates') }} c
{% for g in ['star_dynamics', 'activity', 'stargazers', 'tastemaker', 'owner', 'detail', 'enrich'] %}
left join {{ ref('feat_' ~ g) }} g_{{ g }} on g_{{ g }}.repo_id = c.repo_id and g_{{ g }}.snapshot_date = c.snapshot_date
{% endfor %}
where {{ bucket_filter('c.repo_id') }}
