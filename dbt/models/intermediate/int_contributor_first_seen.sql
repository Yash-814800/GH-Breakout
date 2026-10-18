{#
  Grain (repo_id, actor_id) on young-moving repos: first contribution and its kind.
  Kinds: issue (opened), issue_comment, pull_request (opened), review, push. Where payload detail
  exists (detail_level 1) only `opened` issue/PR events count; before that any issue/PR event is
  used (spine only). Push days have day precision (timestamp = 00:00 of the day).
#}
with y as (select repo_id from {{ ref('int_young_moving_repos') }}),
c as (
    select t.repo_id, t.actor_id, t.created_at as ts, 'issue' as kind
    from {{ ref('stg_issues') }} t semi join y using (repo_id)
    where t.detail_level = 0 or t.action = 'opened'
    union all
    select t.repo_id, t.actor_id, t.created_at, 'issue_comment'
    from {{ ref('stg_issue_comments') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.actor_id, t.created_at, 'pull_request'
    from {{ ref('stg_pull_requests') }} t semi join y using (repo_id)
    where t.detail_level = 0 or t.action = 'opened'
    union all
    select t.repo_id, t.actor_id, t.created_at, 'review'
    from {{ ref('stg_pr_reviews') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.actor_id, t.day::timestamp, 'push'
    from {{ ref('stg_push_daily') }} t semi join y using (repo_id)
)
select repo_id, actor_id,
       min(ts) as first_contribution_at,
       arg_min(kind, ts) as first_contribution_type
from c
group by 1, 2
