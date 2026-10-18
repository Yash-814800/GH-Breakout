{#
  Grain (repo_id, number): pull requests opened on young-moving repos (detail rows only).
  merged_at is set only when a closed event carries pr_merged = true; the merged flag is NULL
  after 2025-10-07 (ADR-007), so merged_at is then NULL, never "not merged".
  first_review_at = first review by someone other than the author after opening.
#}
with y as (select repo_id from {{ ref('int_young_moving_repos') }}),
o as (
    select repo_id, number, created_at as opened_at, actor_id as author_id
    from {{ ref('stg_pull_requests') }} t semi join y using (repo_id)
    where t.detail_level = 1 and t.action = 'opened' and t.number is not null
    qualify row_number() over (partition by repo_id, number order by created_at, event_id) = 1
),
cl as (
    select o.repo_id, o.number, min(p.created_at) as closed_at,
           min(p.created_at) filter (where p.pr_merged) as merged_at
    from o
    join {{ ref('stg_pull_requests') }} p
      on p.repo_id = o.repo_id and p.number = o.number and p.action = 'closed' and p.created_at > o.opened_at
    group by 1, 2
),
rv as (
    select o.repo_id, o.number, min(v.created_at) as first_review_at
    from o
    join {{ ref('stg_pr_reviews') }} v
      on v.repo_id = o.repo_id and v.number = o.number and v.created_at > o.opened_at and v.actor_id <> o.author_id
    group by 1, 2
)
select o.repo_id, o.number, o.opened_at, o.author_id, cl.closed_at, cl.merged_at, rv.first_review_at
from o
left join cl using (repo_id, number)
left join rv using (repo_id, number)
