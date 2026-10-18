{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Candidate-first prefilter (ADR-020). Repos that, on some day d, had >= min_stars_14d stars in
  [d-14, d) while d - first_star_day <= max_age_days + 2. Birth is never later than ~the first star,
  so this is a superset of "young and moving" that does not need the (expensive) birth model; birth
  and everything downstream are computed only for these repos. Breaks the birth <-> young-moving
  dependency cycle. Built per repo_id hash bucket.
#}
with d as (
    select repo_id, day, n_stars,
        min(day) over (partition by repo_id) as first_star_day,
        sum(n_stars) over (partition by repo_id) as n_total
    from {{ ref('int_repo_star_daily') }}
    where {{ bucket_filter('repo_id') }}
),
w as (
    select repo_id, day, first_star_day,
        sum(n_stars) over (
            partition by repo_id order by day
            range between interval 13 days preceding and current row
        ) as stars_14d
    from d
    where n_total >= {{ var('min_stars_14d') }}
)
select {{ bucket_col('repo_id') }} as bucket, repo_id,
       min(first_star_day) as first_star_day, min(day) + 1 as first_qualifying_day
from w
where stars_14d >= {{ var('min_stars_14d') }}
  and (day + 1) - first_star_day <= {{ var('max_age_days') }} + 2
group by 1, 2
