{{ config(materialized='incremental', unique_key=['bucket', 'snapshot_date'], incremental_strategy='delete+insert', on_schema_change='fail') }}
{#
  Tier A. Grain (repo_id, snapshot_date). Star counts, burstiness. Every source row is filtered with
  `day < snapshot_date` / `starred_at < snapshot_date`; windows are [D - n, D). Built per repo_id bucket.
  Gini over the 14 daily counts INCLUDING zero days: with m non-zero days sorted ascending (j = 1..m) the
  zero days take ranks 1..14-m, so the rank of the j-th non-zero day is 14 - m + j and
  G = 2 * sum(rank * x) / (14 * sum(x)) - 15 / 14.
#}
with c as (
    select repo_id, snapshot_date, bucket, age_days from {{ ref('mart_candidates') }}
    where {{ bucket_filter('repo_id') }}
),
sd as (
    select c.repo_id, c.snapshot_date, d.day, d.n_stars
    from c
    join {{ ref('int_repo_star_daily') }} d
      on d.repo_id = c.repo_id and d.day < c.snapshot_date
    where {{ bucket_filter('d.repo_id') }}
),
w14 as (
    select repo_id, snapshot_date, n_stars,
           count(*) over (partition by repo_id, snapshot_date) as m,
           row_number() over (partition by repo_id, snapshot_date order by n_stars, day) as j
    from sd where day >= snapshot_date - 14
),
g as (
    select repo_id, snapshot_date,
           2.0 * sum((14 - m + j) * n_stars) / (14.0 * sum(n_stars)) - 15.0 / 14.0 as star_gini_14d
    from w14 group by 1, 2
),
a as (
    select repo_id, snapshot_date,
        sum(n_stars) filter (where day >= snapshot_date - 1)::integer as stars_1d,
        sum(n_stars) filter (where day >= snapshot_date - 3)::integer as stars_3d,
        sum(n_stars) filter (where day >= snapshot_date - 7)::integer as stars_7d,
        sum(n_stars) filter (where day >= snapshot_date - 14)::integer as stars_14d,
        sum(n_stars) filter (where day >= snapshot_date - 28)::integer as stars_28d,
        sum(n_stars) filter (where day >= snapshot_date - 14 and day < snapshot_date - 7)::integer as stars_prev_7d,
        sum(n_stars)::integer as stars_total_before,
        min(day) as first_star_day,
        count(*) filter (where day >= snapshot_date - 14)::integer as star_active_days_14d,
        max(n_stars) filter (where day >= snapshot_date - 14) as max_day_14d,
        max(day) as max_day
    from sd group by 1, 2
),
h as (
    select c.repo_id, c.snapshot_date, max(n) as max_hour_n, max(ts) as max_ts
    from (
        select c.repo_id, c.snapshot_date, count(*) as n, max(s.starred_at) as ts
        from c
        join {{ ref('stg_stars') }} s
          on s.repo_id = c.repo_id and s.bucket = (c.repo_id % 32)::smallint
         and s.starred_at >= c.snapshot_date - 7 and s.starred_at < c.snapshot_date
        group by c.repo_id, c.snapshot_date, date_trunc('hour', s.starred_at)
    ) c
    group by 1, 2
)
select
    c.bucket, c.repo_id, c.snapshot_date,
    coalesce(a.stars_1d, 0) as stars_1d,
    coalesce(a.stars_3d, 0) as stars_3d,
    coalesce(a.stars_7d, 0) as stars_7d,
    coalesce(a.stars_14d, 0) as stars_14d,
    coalesce(a.stars_28d, 0) as stars_28d,
    a.stars_total_before,
    coalesce(a.stars_7d, 0) - coalesce(a.stars_prev_7d, 0) as star_accel_7d,
    (coalesce(a.stars_7d, 0) + 1.0) / (coalesce(a.stars_prev_7d, 0) + 1.0) as star_ratio_7d,
    c.snapshot_date - a.first_star_day as days_since_first_star,
    c.age_days::integer as age_days,
    coalesce(a.star_active_days_14d, 0) as star_active_days_14d,
    g.star_gini_14d,
    a.max_day_14d::double / nullif(a.stars_14d, 0) as star_max_day_share_14d,
    h.max_hour_n::double / nullif(a.stars_7d, 0) as star_max_hour_share_7d,
    greatest(a.max_day::timestamp, h.max_ts) as _max_input_ts
from c
left join a using (repo_id, snapshot_date)
left join g using (repo_id, snapshot_date)
left join h using (repo_id, snapshot_date)
