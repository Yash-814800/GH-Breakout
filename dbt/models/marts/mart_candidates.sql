{{ config(materialized='incremental', unique_key=['bucket', 'snapshot_date'], incremental_strategy='delete+insert') }}
{#
  Grain (repo_id, snapshot_date): who is scored on snapshot D. THE candidate definition, used unchanged for
  training (snapshot_dates_mode = weekly_history) and for live scoring (mode = single). A repo is a
  candidate on D iff
    birth_at < D and D - birth_day <= max_age_days
    stars before D < max_stars_total, stars in [D-14, D) >= min_stars_14d
    not a fork (exclude_forks), not mirror-like, owner not a bot (exclude_bot_owned), not left-censored
  Unknown metadata (not_found repos) is unknown, not "not a fork" (ADR-017): those repos are kept.

  Star windows use one cumulative-sum table per repo and four ASOF lookups ("cumulative stars on the
  last star day < X" for X = D, D-1, D-7, D-14), not window sums per (repo, D) pair. Differences of
  those give stars_1d, stars_7d, stars_prev_7d [D-14, D-7) and stars_14d. This touches each star-day row
  once per lookup instead of once per candidate window and needs no per-pair scan of int_repo_star_daily.
  Built per repo_id hash bucket (ADR-020); `bucket` unset builds everything (live mode, tests).
  repo_name_at_D is the name last seen before D (display only; the bot-owner rule reads its owner part).
#}
with repos as (
    select y.repo_id, b.birth_at, b.birth_at::date as birth_day, b.birth_source, y.first_moving_day
    from {{ ref('int_young_moving_repos') }} y
    join {{ ref('int_repo_birth') }} b using (repo_id)
    where {{ bucket_filter('y.repo_id') }}
      and not b.is_mirror_like
      {% if var('exclude_forks') %}and not b.is_fork{% endif %}
),
pairs as (
    select r.*, s.snapshot_date
    from repos r
    join {{ ref('mart_snapshot_dates') }} s
      on s.snapshot_date > r.birth_day
     and s.snapshot_date - r.birth_day <= {{ var('max_age_days') }}
     and s.snapshot_date >= r.first_moving_day
),
cum as (
    select repo_id, day, sum(n_stars) over (partition by repo_id order by day) as c
    from {{ ref('int_repo_star_daily') }}
    where {{ bucket_filter('repo_id') }}
      and repo_id in (select repo_id from repos)
),
counted as (
    select p.repo_id, p.snapshot_date, p.birth_at, p.birth_source,
           p.snapshot_date - p.birth_day as age_days,
           coalesce(c0.c, 0) as c_d,
           coalesce(c1.c, 0) as c_d1,
           coalesce(c7.c, 0) as c_d7,
           coalesce(c14.c, 0) as c_d14
    from pairs p
    asof left join cum c0 on p.repo_id = c0.repo_id and p.snapshot_date > c0.day
    asof left join cum c1 on p.repo_id = c1.repo_id and p.snapshot_date - 1 > c1.day
    asof left join cum c7 on p.repo_id = c7.repo_id and p.snapshot_date - 7 > c7.day
    asof left join cum c14 on p.repo_id = c14.repo_id and p.snapshot_date - 14 > c14.day
),
moving as (
    select repo_id, snapshot_date, birth_at, birth_source, age_days,
           (c_d)::integer as stars_total_before,
           (c_d - c_d1)::integer as stars_1d,
           (c_d - c_d7)::integer as stars_7d,
           (c_d7 - c_d14)::integer as stars_prev_7d,
           (c_d - c_d14)::integer as stars_14d
    from counted
    where c_d < {{ var('max_stars_total') }}
      and c_d - c_d14 >= {{ var('min_stars_14d') }}
),
names as (
    select repo_id, repo_name, first_seen
    from {{ ref('stg_repo_name_history') }}
    where repo_id in (select repo_id from moving)
),
bot_logins as (
    select lower(login) as login from {{ ref('known_bots') }}
    union
    select lower(s.bot_like_login)
    from {{ ref('stg_bot_actor_signals') }} s
    join {{ ref('stg_bot_actors') }} using (actor_id)
    where s.bot_like_login is not null
),
named as (
    select m.*, n.repo_name as repo_name_at_D, md.owner_id
    from moving m
    asof left join names n on m.repo_id = n.repo_id and m.snapshot_date > n.first_seen
    left join {{ ref('stg_repo_metadata') }} md on md.repo_id = m.repo_id and md.status = 'ok'
)
select
    {{ bucket_col('repo_id') }} as bucket,
    repo_id, snapshot_date, birth_at, age_days, stars_total_before,
    stars_1d, stars_7d, stars_14d, stars_prev_7d, birth_source, repo_name_at_D
from named
{% if var('exclude_bot_owned') %}
where not (
    regexp_matches(split_part(coalesce(repo_name_at_D, ''), '/', 1), '(\[bot\]|[-_]bot)$', 'i')
    or lower(split_part(coalesce(repo_name_at_D, ''), '/', 1)) in (select login from bot_logins)
    or coalesce(owner_id in (select actor_id from {{ ref('stg_bot_actors') }}), false)
)
{% endif %}
