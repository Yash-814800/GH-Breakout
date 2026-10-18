{#
  Grain (repo_id, number): issues opened on young-moving repos (detail rows only, i.e. from
  detail_start_date). first_response_at = first non-bot comment by someone other than the author
  after opening; closed_at = first `closed` event after opening. Timestamps only; Phase 7 applies the
  "before D" cut.
#}
with y as (select repo_id from {{ ref('int_young_moving_repos') }}),
o as (
    select repo_id, number, created_at as opened_at, actor_id as author_id
    from {{ ref('stg_issues') }} t semi join y using (repo_id)
    where t.detail_level = 1 and t.action = 'opened' and t.number is not null
    qualify row_number() over (partition by repo_id, number order by created_at, event_id) = 1
),
r as (
    select o.repo_id, o.number, min(c.created_at) as first_response_at
    from o
    join {{ ref('stg_issue_comments') }} c
      on c.repo_id = o.repo_id and c.number = o.number
     and c.created_at > o.opened_at and c.actor_id <> o.author_id
    where c.is_pull_request = false
    group by 1, 2
),
cl as (
    select o.repo_id, o.number, min(i.created_at) as closed_at
    from o
    join {{ ref('stg_issues') }} i
      on i.repo_id = o.repo_id and i.number = o.number and i.action = 'closed' and i.created_at > o.opened_at
    group by 1, 2
)
select o.repo_id, o.number, o.opened_at, o.author_id, r.first_response_at, cl.closed_at
from o
left join r using (repo_id, number)
left join cl using (repo_id, number)
