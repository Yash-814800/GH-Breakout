{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Grain: one row per early first star on a young-moving repo (int_early_stars).
  est_account_created_at: ASOF join on the actor-id age map (ids below the first breakpoint take the
  oldest estimate; est_is_extrapolated marks ids above the last breakpoint). Prior-90d activity is
  cumulative(star_day - 1) - cumulative(star_day - 91): strictly before the star day, via ASOF joins.
#}
with age_bounds as (
    select max(actor_id_breakpoint) as max_bp, min(est_created_at) as min_est
    from {{ ref('stg_actor_age_map') }}
),
s as (select * from {{ ref('int_early_stars') }} where {{ bucket_filter('actor_id') }}),
aged as (
    select s.*, coalesce(m.est_created_at, ab.min_est) as est_account_created_at,
           s.actor_id > ab.max_bp as est_is_extrapolated
    from s cross join age_bounds ab
    asof left join {{ ref('stg_actor_age_map') }} m on s.actor_id >= m.actor_id_breakpoint
),
cum as (
    select actor_id, day, cum_events, cum_repo_days, cum_stars_given
    from {{ ref('int_actor_cumulative_activity') }}
    where {{ ('bucket = ' ~ var('bucket')) if var('bucket', none) is not none else 'true' }}
),
q1 as (
    select a.repo_id, a.actor_id, c.cum_events, c.cum_repo_days, c.cum_stars_given
    from aged a
    asof left join cum c
        on a.actor_id = c.actor_id and a.star_day - 1 >= c.day
),
q2 as (
    select a.repo_id, a.actor_id, c.cum_events, c.cum_repo_days, c.cum_stars_given
    from aged a
    asof left join cum c
        on a.actor_id = c.actor_id and a.star_day - 91 >= c.day
),
sd as (
    select actor_id, day, n_stars_given from {{ ref('int_actor_daily_activity') }}
    where {{ ('bucket = ' ~ var('bucket')) if var('bucket', none) is not none else 'true' }}
)
select
    {{ bucket_col('a.actor_id') }} as bucket,
    a.repo_id, a.actor_id, a.starred_at, a.star_day,
    a.est_account_created_at, a.est_is_extrapolated,
    date_diff('day', a.est_account_created_at, a.starred_at)::integer as account_age_days_at_star,
    (coalesce(q1.cum_events, 0) - coalesce(q2.cum_events, 0))::bigint as actor_events_prior_90d,
    (coalesce(q1.cum_repo_days, 0) - coalesce(q2.cum_repo_days, 0))::bigint as actor_repos_prior_90d,
    (coalesce(q1.cum_stars_given, 0) - coalesce(q2.cum_stars_given, 0))::bigint as actor_stars_prior_90d,
    coalesce(sd.n_stars_given, 0)::integer as actor_stars_same_day
from aged a
left join q1 using (repo_id, actor_id)
left join q2 using (repo_id, actor_id)
left join sd on sd.actor_id = a.actor_id and sd.day = a.star_day
