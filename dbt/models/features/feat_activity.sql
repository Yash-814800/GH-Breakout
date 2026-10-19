{{ config(materialized='incremental', unique_key=['bucket', 'snapshot_date'], incremental_strategy='delete+insert', on_schema_change='fail') }}
{#
  Tier A (all-era spine counts). Grain (repo_id, snapshot_date). Daily counts come from
  int_repo_daily_activity (day < D), people from int_core_actors_daily and int_contributor_sessions.
  Sessions: a session is known to have STARTED before D from earlier events alone, so start-based counts
  (sessions, distinct / new contributors) use `session_start in [D - 28, D)`. End, length and size depend on
  later events: they only use sessions that are complete as of D, i.e. session_end + session_gap_minutes
  < D (an event after D within the gap would have extended it). actor_days_14d is the sum of the daily
  distinct-actor counts (actor-days), not distinct actors over the window.
#}
with c as (
    select repo_id, snapshot_date, bucket from {{ ref('mart_candidates') }}
    where {{ bucket_filter('repo_id') }}
),
da as (
    select c.repo_id, c.snapshot_date, d.day, d.n_stars, d.n_forks, d.n_issue_events, d.n_comment_events,
           d.n_pr_events, d.n_reviews, d.n_releases, d.n_pushes, d.n_distinct_actors
    from c
    join {{ ref('int_repo_daily_activity') }} d
      on d.repo_id = c.repo_id and d.day < c.snapshot_date
    where {{ bucket_filter('d.repo_id') }}
),
daily as (
    select repo_id, snapshot_date,
        sum(n_forks) filter (where day >= snapshot_date - 7)::integer as forks_7d,
        sum(n_forks) filter (where day >= snapshot_date - 14)::integer as forks_14d,
        sum(n_stars) filter (where day >= snapshot_date - 14)::integer as stars_14d,
        sum(n_distinct_actors) filter (where day >= snapshot_date - 14)::integer as actor_days_14d,
        sum(n_issue_events) filter (where day >= snapshot_date - 14)::integer as issue_events_14d,
        sum(n_comment_events) filter (where day >= snapshot_date - 14)::integer as comment_events_14d,
        sum(n_pr_events) filter (where day >= snapshot_date - 14)::integer as pr_events_14d,
        sum(n_reviews) filter (where day >= snapshot_date - 14)::integer as reviews_14d,
        sum(n_pushes) filter (where day >= snapshot_date - 14)::integer as pushes_14d,
        sum(n_releases)::integer as releases_total_before,
        snapshot_date - max(day) filter (where n_releases > 0) as days_since_last_release,
        count(*) filter (where n_pushes > 0 and day >= snapshot_date - 14)::integer as push_active_days_14d,
        max(day) as max_day
    from da group by 1, 2
),
pushers as (
    select c.repo_id, c.snapshot_date, count(distinct k.actor_id)::integer as distinct_pushers_28d,
           max(k.day) as max_day
    from c
    join {{ ref('int_core_actors_daily') }} k
      on k.repo_id = c.repo_id and k.pushed and k.day >= c.snapshot_date - 28 and k.day < c.snapshot_date
    group by 1, 2
),
ss as (
    select c.repo_id, c.snapshot_date, s.actor_id, s.session_id, s.session_start, s.session_end, s.n_events,
           s.session_end < c.snapshot_date - interval '{{ var("session_gap_minutes") }} minutes' as is_complete
    from c
    join {{ ref('int_contributor_sessions') }} s
      on s.repo_id = c.repo_id and s.session_start >= c.snapshot_date - 28 and s.session_start < c.snapshot_date
    where {{ bucket_filter('s.repo_id') }}
),
sess as (
    select repo_id, snapshot_date,
        count(*)::integer as sessions_28d,
        count(distinct actor_id)::integer as distinct_contributors_28d,
        count(distinct actor_id) filter (where session_id = 1)::integer as new_contributors_28d,
        median(date_diff('second', session_start, session_end) / 60.0) filter (where is_complete) as median_session_minutes_28d,
        count(distinct actor_id) filter (where is_complete)::integer as distinct_session_actors_28d,
        max(session_start) as max_start,
        max(session_end) filter (where is_complete) as max_end
    from ss group by 1, 2
),
top_actor as (
    select repo_id, snapshot_date, max(ev)::double / sum(ev) as top_actor_share_28d
    from (
        select repo_id, snapshot_date, actor_id, sum(n_events) as ev
        from ss where is_complete group by 1, 2, 3
    ) group by 1, 2
)
select
    c.bucket, c.repo_id, c.snapshot_date,
    coalesce(d.forks_7d, 0) as forks_7d,
    coalesce(d.forks_14d, 0) as forks_14d,
    coalesce(d.forks_14d, 0) / (coalesce(d.stars_14d, 0) + 1.0) as fork_star_ratio_14d,
    coalesce(d.actor_days_14d, 0) as actor_days_14d,
    coalesce(d.issue_events_14d, 0) as issue_events_14d,
    coalesce(d.comment_events_14d, 0) as comment_events_14d,
    coalesce(d.pr_events_14d, 0) as pr_events_14d,
    coalesce(d.reviews_14d, 0) as reviews_14d,
    coalesce(d.releases_total_before, 0) as releases_total_before,
    d.days_since_last_release,
    coalesce(d.push_active_days_14d, 0) as push_active_days_14d,
    coalesce(p.distinct_pushers_28d, 0) as distinct_pushers_28d,
    {{ shannon_entropy_bits([
        'coalesce(d.stars_14d, 0)', 'coalesce(d.forks_14d, 0)', 'coalesce(d.issue_events_14d, 0)',
        'coalesce(d.comment_events_14d, 0)', 'coalesce(d.pr_events_14d, 0)', 'coalesce(d.reviews_14d, 0)',
        'coalesce(d.pushes_14d, 0)']) }} as event_type_entropy_14d,
    coalesce(s.distinct_contributors_28d, 0) as distinct_contributors_28d,
    coalesce(s.new_contributors_28d, 0) as new_contributors_28d,
    coalesce(s.new_contributors_28d, 0)::double / nullif(s.distinct_contributors_28d, 0) as first_time_contributor_rate_28d,
    t.top_actor_share_28d,
    coalesce(s.sessions_28d, 0) as sessions_28d,
    s.median_session_minutes_28d,
    coalesce(s.distinct_session_actors_28d, 0) as distinct_session_actors_28d,
    greatest(d.max_day::timestamp, p.max_day::timestamp, s.max_start, s.max_end) as _max_input_ts
from c
left join daily d using (repo_id, snapshot_date)
left join pushers p using (repo_id, snapshot_date)
left join sess s using (repo_id, snapshot_date)
left join top_actor t using (repo_id, snapshot_date)
