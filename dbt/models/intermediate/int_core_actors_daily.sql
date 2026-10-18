{#
  Grain (repo_id, actor_id, day): evidence that an actor acts as a maintainer of a young-moving
  repo that day: pushed, closed a PR (detail eras only), or is the repo owner (the owner segment of
  the repo name ON THE EVENT equals the actor login, case-insensitive; the name is read from the
  event itself, so renames are handled). Phase 7 uses a trailing window of this.
#}
with y as (select repo_id from {{ ref('int_young_moving_repos') }}),
ev as (
    select t.repo_id, t.actor_id, t.created_at::date as day,
           false as pushed, (t.action = 'closed') as closed_pr,
           lower(split_part(t.repo_name, '/', 1)) = lower(t.actor_login) as is_owner
    from {{ ref('stg_pull_requests') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.actor_id, t.created_at::date, false, false,
           lower(split_part(t.repo_name, '/', 1)) = lower(t.actor_login)
    from {{ ref('stg_issues') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.actor_id, t.created_at::date, false, false,
           lower(split_part(t.repo_name, '/', 1)) = lower(t.actor_login)
    from {{ ref('stg_issue_comments') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.actor_id, t.created_at::date, false, false,
           lower(split_part(t.repo_name, '/', 1)) = lower(t.actor_login)
    from {{ ref('stg_creates') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.actor_id, t.created_at::date, false, false,
           lower(split_part(t.repo_name, '/', 1)) = lower(t.actor_login)
    from {{ ref('stg_pr_reviews') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.actor_id, t.day, true, false, false
    from {{ ref('stg_push_daily') }} t semi join y using (repo_id)
)
select repo_id, actor_id, day,
       coalesce(bool_or(pushed), false) as pushed,
       coalesce(bool_or(closed_pr), false) as closed_pr,
       coalesce(bool_or(is_owner), false) as is_owner
from ev
group by 1, 2, 3
having bool_or(pushed) or coalesce(bool_or(closed_pr), false) or coalesce(bool_or(is_owner), false)
