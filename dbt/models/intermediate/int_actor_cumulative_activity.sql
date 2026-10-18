{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Grain (actor_id, day): running totals as of the END of `day` (rows exist only on active days).
  cum_repo_days is the running sum of daily distinct-repo counts (a repo touched on two days counts
  twice), which is additive and so supports cumulative(day-1) - cumulative(day-91).
#}
select bucket, actor_id, day,
    sum(n_events) over w as cum_events,
    sum(n_repos) over w as cum_repo_days,
    sum(n_stars_given) over w as cum_stars_given
from {{ ref('int_actor_daily_activity') }}
where {{ ('bucket = ' ~ var('bucket')) if var('bucket', none) is not none else 'true' }}
window w as (partition by actor_id order by day rows between unbounded preceding and current row)
