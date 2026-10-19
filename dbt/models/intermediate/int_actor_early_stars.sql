{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Tastemaker input (Phase 7, ADR-022). Grain (repo_id, actor_id): every EARLY first star, i.e. a star made
  while the repo had < max_stars_total stars and was at most max_age_days old (the candidate universe).
    is_hit       the repo gained >= absolute_min_gain first stars on the days (star_day, star_day + L]
                 (L = tm_lookahead_days). Absolute on purpose: independent of the snapshot grid and of the
                 relative label.
    outcome_day  star_day + L: the last day the hit depends on. The outcome is known on every snapshot
                 D > outcome_day, so consumers must join with `D > outcome_day` (strictly).
  Day granularity: stars later on star_day itself are not counted, the window ends with a whole day.
  Built per repo_id hash bucket (ADR-020).
#}
with e as (
    select s.repo_id, s.actor_id, s.starred_at, s.star_day, b.birth_at::date as birth_day,
           row_number() over (partition by s.repo_id order by s.starred_at, s.event_id) as star_rank
    from {{ ref('int_early_stars') }} s
    join {{ ref('int_repo_birth') }} b using (repo_id)
    where {{ bucket_filter('s.repo_id') }}
),
early as (
    select * from e
    where star_rank <= {{ var('max_stars_total') }}
      and star_day - birth_day <= {{ var('max_age_days') }}
),
cum as (
    select repo_id, day, sum(n_stars) over (partition by repo_id order by day) as c
    from {{ ref('int_repo_star_daily') }}
    where {{ bucket_filter('repo_id') }}
      and repo_id in (select repo_id from early)
)
select
    {{ bucket_col('e.repo_id') }} as bucket,
    e.repo_id, e.actor_id, e.starred_at, e.star_day,
    e.star_day + {{ var('tm_lookahead_days') }} as outcome_day,
    (coalesce(c2.c, 0) - coalesce(c1.c, 0))::integer as gain_lookahead,
    coalesce(c2.c, 0) - coalesce(c1.c, 0) >= {{ var('absolute_min_gain') }} as is_hit
from early e
asof left join cum c1 on e.repo_id = c1.repo_id and e.star_day >= c1.day
asof left join cum c2 on e.repo_id = c2.repo_id and e.star_day + {{ var('tm_lookahead_days') }} >= c2.day
