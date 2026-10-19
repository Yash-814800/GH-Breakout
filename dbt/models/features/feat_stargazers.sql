{{ config(materialized='incremental', unique_key=['bucket', 'snapshot_date'], incremental_strategy='delete+insert', on_schema_change='fail') }}
{#
  Tier A + actor-age enrichment. Grain (repo_id, snapshot_date).
  Quality of the first stars in [D - 14, D) from int_star_events_enriched (actor activity is strictly before
  the star day, the account age comes from the immutable actor id).
  Retention so far: of the stargazers who starred in [D - 28, D - 7), the share who ALSO forked, opened an
  issue / PR or commented on the repo before D (int_stargazer_later_actions with action_at < D).
#}
with c as (
    select repo_id, snapshot_date, bucket from {{ ref('mart_candidates') }}
    where {{ bucket_filter('repo_id') }}
),
q as (
    select c.repo_id, c.snapshot_date,
        count(*)::integer as sg_n,
        avg((e.actor_events_prior_90d >= 10 and e.actor_repos_prior_90d >= 2)::integer) as sg_share_experienced,
        median(e.account_age_days_at_star) as sg_median_account_age_days,
        avg((e.account_age_days_at_star < 30)::integer) as sg_share_account_lt_30d,
        avg((e.actor_events_prior_90d = 0)::integer) as sg_share_zero_prior_activity,
        median(e.actor_stars_same_day) as sg_median_stars_same_day,
        avg((e.actor_stars_same_day >= 50)::integer) as sg_share_bulk_starrers,
        max(e.starred_at) as max_ts
    from c
    join {{ ref('int_star_events_enriched') }} e
      on e.repo_id = c.repo_id and e.star_day >= c.snapshot_date - 14 and e.star_day < c.snapshot_date
    group by 1, 2
),
r as (
    select c.repo_id, c.snapshot_date, e.actor_id
    from c
    join {{ ref('int_early_stars') }} e
      on e.repo_id = c.repo_id and e.star_day >= c.snapshot_date - 28 and e.star_day < c.snapshot_date - 7
),
ra as (
    select r.repo_id, r.snapshot_date, r.actor_id,
           bool_or(a.action_type = 'fork') as did_fork,
           bool_or(a.action_type in ('issue', 'pull_request')) as did_issue_or_pr,
           max(a.action_at) as max_ts
    from r
    join {{ ref('int_stargazer_later_actions') }} a
      on a.repo_id = r.repo_id and a.actor_id = r.actor_id and a.action_at < r.snapshot_date
    where {{ bucket_filter('a.repo_id') }}
    group by 1, 2, 3
),
ret as (
    select r.repo_id, r.snapshot_date, r.n, coalesce(a.n_any, 0) as n_any, coalesce(a.n_fork, 0) as n_fork,
           coalesce(a.n_ip, 0) as n_ip, a.max_ts
    from (select repo_id, snapshot_date, count(*) as n from r group by 1, 2) r
    left join (
        select repo_id, snapshot_date, count(*) as n_any, count(*) filter (where did_fork) as n_fork,
               count(*) filter (where did_issue_or_pr) as n_ip, max(max_ts) as max_ts
        from ra group by 1, 2
    ) a using (repo_id, snapshot_date)
)
select
    c.bucket, c.repo_id, c.snapshot_date,
    coalesce(q.sg_n, 0) as sg_n,
    q.sg_share_experienced, q.sg_median_account_age_days, q.sg_share_account_lt_30d,
    q.sg_share_zero_prior_activity, q.sg_median_stars_same_day, q.sg_share_bulk_starrers,
    ret.n_any::double / ret.n as sg_retention_any_28d,
    ret.n_fork::double / ret.n as sg_retention_fork_28d,
    ret.n_ip::double / ret.n as sg_retention_issue_or_pr_28d,
    greatest(q.max_ts, ret.max_ts) as _max_input_ts
from c
left join q using (repo_id, snapshot_date)
left join ret using (repo_id, snapshot_date)
