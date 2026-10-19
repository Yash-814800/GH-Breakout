{#
  Leakage guard (Phase 7, 7.2.3): the newest source timestamp that fed each feature group's row must be
  strictly before the snapshot date. Returns the offending rows (the test passes with 0 rows).
#}
{% set groups = ['star_dynamics', 'activity', 'stargazers', 'tastemaker', 'owner', 'detail', 'enrich'] %}
{% for g in groups %}
select '{{ g }}' as feature_group, repo_id, snapshot_date, _max_input_ts
from {{ ref('feat_' ~ g) }}
where _max_input_ts >= snapshot_date
{{ 'union all' if not loop.last }}
{% endfor %}
