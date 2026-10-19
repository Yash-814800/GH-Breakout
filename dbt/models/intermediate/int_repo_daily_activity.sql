{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Grain (repo_id, day) for young-moving repos over the whole window. One UNION ALL of slim
  per-type projections, then one GROUP BY. Counts that need payload detail (action, ref_type,
  is_pull_request, merged flag) are NULL on days before detail_start_date (detail_level 0), never 0.
  n_issue_events, n_comment_events and n_pr_events count every event of the type (all eras, spine only);
  Phase 7 uses them for era-independent activity features. Bots are excluded in staging. Built in 16 repo_id hash buckets (ADR-020).
#}
with y as (select repo_id from {{ ref('int_young_moving_repos') }} where {{ bucket_filter('repo_id') }}),
u as (
    select s.repo_id, s.starred_at::date as day, s.actor_id, 'star' as k, null as a, null as flag, null::tinyint as dl, 1 as n
    from {{ ref('stg_stars') }} s semi join y using (repo_id)
    union all
    select t.repo_id, t.created_at::date, t.actor_id, 'fork', null, null, t.detail_level, 1 as n
    from {{ ref('stg_forks') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.created_at::date, t.actor_id, 'issue', t.action, null, t.detail_level, 1 as n
    from {{ ref('stg_issues') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.created_at::date, t.actor_id, 'issue_comment', null, t.is_pull_request, t.detail_level, 1 as n
    from {{ ref('stg_issue_comments') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.created_at::date, t.actor_id, 'pr', t.action, t.pr_merged, t.detail_level, 1 as n
    from {{ ref('stg_pull_requests') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.created_at::date, t.actor_id, 'review', null, null, t.detail_level, 1 as n
    from {{ ref('stg_pr_reviews') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.created_at::date, t.actor_id, 'release', null, null, t.detail_level, 1 as n
    from {{ ref('stg_releases') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.created_at::date, t.actor_id, 'create', t.ref_type, null, t.detail_level, 1 as n
    from {{ ref('stg_creates') }} t semi join y using (repo_id)
    union all
    select t.repo_id, t.created_at::date, t.actor_id, 'public', null, null, t.detail_level, 1 as n
    from {{ ref('stg_public_events') }} t semi join y using (repo_id)
    union all
    select p.repo_id, p.day, p.actor_id, 'push', null, null, null::tinyint, p.n_pushes
    from {{ ref('stg_push_daily') }} p semi join y using (repo_id)
),
ev as (
    select repo_id, day,
        count(*) filter (where k = 'star')::integer as n_stars,
        count(*) filter (where k = 'fork')::integer as n_forks,
        count(*) filter (where k = 'issue')::integer as n_issue_events,
        count(*) filter (where k = 'issue' and a = 'opened')::integer as _issues_opened,
        count(*) filter (where k = 'issue' and a = 'closed')::integer as _issues_closed,
        count(*) filter (where k = 'issue_comment')::integer as n_comment_events,
        count(*) filter (where k = 'pr')::integer as n_pr_events,
        count(*) filter (where k = 'issue_comment' and flag = false)::integer as _issue_comments,
        count(*) filter (where k = 'issue_comment' and flag = true)::integer as _pr_comments,
        count(*) filter (where k = 'pr' and a = 'opened')::integer as _prs_opened,
        count(*) filter (where k = 'pr' and a = 'closed')::integer as _prs_closed,
        count(*) filter (where k = 'pr' and a = 'closed' and flag = true)::integer as _prs_merged,
        count(*) filter (where k = 'review')::integer as n_reviews,
        count(*) filter (where k = 'release')::integer as n_releases,
        count(*) filter (where k = 'create' and a = 'branch')::integer as _creates_branch,
        count(*) filter (where k = 'create' and a = 'tag')::integer as _creates_tag,
        coalesce(sum(n) filter (where k = 'push'), 0)::integer as n_pushes,
        count(distinct actor_id) filter (where k = 'push')::integer as n_pushers,
        count(distinct actor_id)::integer as n_distinct_actors,
        min(dl)::tinyint as detail_level_min
    from u
    group by 1, 2
),
j as (select * from ev)
select
    {{ bucket_col('repo_id') }} as bucket, repo_id, day,
    coalesce(n_stars, 0) as n_stars,
    coalesce(n_forks, 0) as n_forks,
    case when day >= date '{{ var("detail_start_date") }}' then coalesce(_issues_opened, 0) end as n_issues_opened,
    case when day >= date '{{ var("detail_start_date") }}' then coalesce(_issues_closed, 0) end as n_issues_closed,
    coalesce(n_issue_events, 0) as n_issue_events,
    coalesce(n_comment_events, 0) as n_comment_events,
    coalesce(n_pr_events, 0) as n_pr_events,
    case when day >= date '{{ var("detail_start_date") }}' then coalesce(_issue_comments, 0) end as n_issue_comments,
    case when day >= date '{{ var("detail_start_date") }}' then coalesce(_pr_comments, 0) end as n_pr_comments,
    case when day >= date '{{ var("detail_start_date") }}' then coalesce(_prs_opened, 0) end as n_prs_opened,
    case when day >= date '{{ var("detail_start_date") }}' then coalesce(_prs_closed, 0) end as n_prs_closed,
    case when day >= date '{{ var("detail_start_date") }}' then coalesce(_prs_merged, 0) end as n_prs_merged,
    coalesce(n_reviews, 0) as n_reviews,
    coalesce(n_releases, 0) as n_releases,
    case when day >= date '{{ var("detail_start_date") }}' then coalesce(_creates_branch, 0) end as n_creates_branch,
    case when day >= date '{{ var("detail_start_date") }}' then coalesce(_creates_tag, 0) end as n_creates_tag,
    n_pushes,
    n_pushers,
    n_distinct_actors,
    detail_level_min
from j
