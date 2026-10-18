{#
  First stars on young-moving repos that can matter for a snapshot: starred_at < birth + max_age_days
  + 1 day (a candidate at D has age <= max_age_days, so features at D only see these stars).
  Stars given before the recorded birth are kept. Later stars only count towards labels, which
  use int_repo_star_daily. Grain (repo_id, actor_id).
#}
select s.repo_id, s.actor_id, s.starred_at, s.starred_at::date as star_day, s.event_id
from {{ ref('stg_stars') }} s
join {{ ref('int_young_moving_repos') }} y using (repo_id)
join {{ ref('int_repo_birth') }} b using (repo_id)
where s.starred_at < b.birth_at + interval '{{ var("max_age_days") + 1 }} days'
