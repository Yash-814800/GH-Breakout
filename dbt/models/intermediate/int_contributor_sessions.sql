{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Sessionization of non-push human activity (issues, comments, PRs, reviews) on young-moving
  repos. A new session starts when the gap to the actor's previous event on the repo exceeds
  session_gap_minutes. Grain (repo_id, actor_id, session_id); session_id counts from 1 per pair.
#}
with y as (select repo_id from {{ ref('int_young_moving_repos') }} where {{ bucket_filter('repo_id') }}),
e as (
    select t.repo_id, t.actor_id, t.created_at, 'issue' as kind from {{ ref('stg_issues') }} t semi join y using (repo_id)
    union all select t.repo_id, t.actor_id, t.created_at, 'issue_comment' from {{ ref('stg_issue_comments') }} t semi join y using (repo_id)
    union all select t.repo_id, t.actor_id, t.created_at, 'pull_request' from {{ ref('stg_pull_requests') }} t semi join y using (repo_id)
    union all select t.repo_id, t.actor_id, t.created_at, 'review' from {{ ref('stg_pr_reviews') }} t semi join y using (repo_id)
),
g as (
    select *,
        case when lag(created_at) over w is null
               or created_at - lag(created_at) over w > interval '{{ var("session_gap_minutes") }} minutes'
             then 1 else 0 end as is_new
    from e
    window w as (partition by repo_id, actor_id order by created_at)
),
s as (
    select *, sum(is_new) over (partition by repo_id, actor_id order by created_at
                                rows between unbounded preceding and current row) as session_id
    from g
)
select {{ bucket_col('repo_id') }} as bucket, repo_id, actor_id, session_id::integer as session_id,
       min(created_at) as session_start, max(created_at) as session_end,
       count(*)::integer as n_events,
       list_sort(list_distinct(list(kind))) as event_types
from s
group by 1, 2, 3, 4
