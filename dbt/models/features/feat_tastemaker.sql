{{ config(materialized='incremental', unique_key=['bucket', 'snapshot_date'], incremental_strategy='delete+insert', on_schema_change='fail') }}
{#
  Tier A, the co-star signal. Grain (repo_id, snapshot_date).
  For each first star in [D - 14, D) take the stargazer's tastemaker state: the number of early stars whose
  60-day outcome was fully known BEFORE D (outcome_day < D, strictly; int_actor_early_cum) and how many of
  those were hits. Smoothed score = (hits + alpha) / (early_known + alpha + beta); an actor without known
  early stars gets the prior alpha / (alpha + beta). 'Top' stargazers have early_known >= tm_min_known and a
  score at or above the top-q threshold as of the last month boundary before D (int_tastemaker_thresholds).
  The stargazer's own star in this window can never have a known outcome (< 60 days old).
  _max_input_ts: the month threshold M is built from outcomes with outcome_day < M, so the newest day it used
  is M - 1 day (M itself can equal D on the first of a month).
#}
with c as (
    select repo_id, snapshot_date, bucket from {{ ref('mart_candidates') }}
    where {{ bucket_filter('repo_id') }}
),
sg as (
    select c.repo_id, c.snapshot_date, s.actor_id, s.starred_at
    from c
    join {{ ref('int_early_stars') }} s
      on s.repo_id = c.repo_id and s.star_day >= c.snapshot_date - 14 and s.star_day < c.snapshot_date
),
k as (
    select actor_id, outcome_day, early_stars_known, hits_known
    from {{ ref('int_actor_early_cum') }}
    where actor_id in (select actor_id from sg)
),
st as (
    select sg.repo_id, sg.snapshot_date, sg.starred_at, k.outcome_day,
           coalesce(k.early_stars_known, 0) as n_known,
           (coalesce(k.hits_known, 0) + {{ var('tm_alpha') }})
             / (coalesce(k.early_stars_known, 0) + {{ var('tm_alpha') }} + {{ var('tm_beta') }}) as tm_score,
           date_trunc('month', sg.snapshot_date)::date as month
    from sg
    asof left join k on sg.actor_id = k.actor_id and sg.snapshot_date > k.outcome_day
),
sc as (
    select st.*, t.score_threshold, t.month as threshold_month
    from st
    asof left join {{ ref('int_tastemaker_thresholds') }} t on st.month >= t.month
),
agg as (
    select repo_id, snapshot_date,
        avg(tm_score) as sg_tm_mean_14d,
        max(tm_score) as sg_tm_max_14d,
        count(*) filter (where n_known >= {{ var('tm_min_known') }} and tm_score >= score_threshold)::integer as sg_tm_top_count_14d,
        avg((n_known > 0)::integer) as sg_tm_known_share_14d,
        greatest(max(starred_at), max(outcome_day)::timestamp, max(threshold_month)::timestamp - interval 1 day) as max_ts
    from sc group by 1, 2
)
select c.bucket, c.repo_id, c.snapshot_date,
       a.sg_tm_mean_14d, a.sg_tm_max_14d, a.sg_tm_top_count_14d, a.sg_tm_known_share_14d,
       a.max_ts as _max_input_ts
from c left join agg a using (repo_id, snapshot_date)
