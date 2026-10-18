{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Event-level link: for each early stargazer of a young-moving repo, their later actions on the SAME
  repo within 90 days after the star (fork, issue opened, PR opened, comment). Grain
  (repo_id, actor_id, action_event_id). Point-in-time features (Phase 7) filter
  action_at < D. Issue/PR `opened` is required where detail exists; with spine-only rows any
  issue/PR event counts.
#}
with s as (select repo_id, actor_id, starred_at from {{ ref('int_early_stars') }} where {{ bucket_filter('repo_id') }}),
a as (
    select repo_id, actor_id, created_at as action_at, event_id as action_event_id, 'fork' as action_type from {{ ref('stg_forks') }} where {{ bucket_filter('repo_id') }}
    union all
    select repo_id, actor_id, created_at, event_id, 'issue' from {{ ref('stg_issues') }} where {{ bucket_filter('repo_id') }} and (detail_level = 0 or action = 'opened')
    union all
    select repo_id, actor_id, created_at, event_id, 'pull_request' from {{ ref('stg_pull_requests') }} where {{ bucket_filter('repo_id') }} and (detail_level = 0 or action = 'opened')
    union all
    select repo_id, actor_id, created_at, event_id, 'comment' from {{ ref('stg_issue_comments') }} where {{ bucket_filter('repo_id') }}
)
select {{ bucket_col('s.repo_id') }} as bucket, s.repo_id, s.actor_id, s.starred_at, a.action_type, a.action_at, a.action_event_id,
       date_diff('day', s.starred_at, a.action_at)::integer as days_after_star
from s
join a on a.repo_id = s.repo_id and a.actor_id = s.actor_id
 and a.action_at > s.starred_at and a.action_at <= s.starred_at + interval 90 day
