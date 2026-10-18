{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Grain (actor_id, day) for actors who gave an early star (int_early_stars) to a young-moving
  repo. Counts all kept, non-bot activity of the actor on ANY repo: n_events (stars, forks, issues,
  comments, PRs, reviews, releases, creates, public events and pushes), n_repos (distinct repos that
  day) and n_stars_given. Built per actor_id hash bucket (ADR-020). Rows are kept only for days up to the actor's last early star and
  from 91 days before their first one (nothing else can enter a 90-day look-back).
#}
with bounds as (
    select actor_id,
           min(star_day) - 91 as lo, max(star_day) as hi
    from {{ ref('int_early_stars') }}
    where {{ bucket_filter('actor_id') }}
    group by 1
),
u as (
    select s.actor_id, s.starred_at::date as day, s.repo_id, 1 as n, 1 as stars from {{ ref('stg_stars') }} s
    where {{ bucket_filter('s.actor_id') }}
    union all select actor_id, created_at::date, repo_id, 1, 0 from {{ ref('stg_forks') }} where {{ bucket_filter('actor_id') }}
    union all select actor_id, created_at::date, repo_id, 1, 0 from {{ ref('stg_issues') }} where {{ bucket_filter('actor_id') }}
    union all select actor_id, created_at::date, repo_id, 1, 0 from {{ ref('stg_issue_comments') }} where {{ bucket_filter('actor_id') }}
    union all select actor_id, created_at::date, repo_id, 1, 0 from {{ ref('stg_pull_requests') }} where {{ bucket_filter('actor_id') }}
    union all select actor_id, created_at::date, repo_id, 1, 0 from {{ ref('stg_pr_reviews') }} where {{ bucket_filter('actor_id') }}
    union all select actor_id, created_at::date, repo_id, 1, 0 from {{ ref('stg_releases') }} where {{ bucket_filter('actor_id') }}
    union all select actor_id, created_at::date, repo_id, 1, 0 from {{ ref('stg_creates') }} where {{ bucket_filter('actor_id') }}
    union all select actor_id, created_at::date, repo_id, 1, 0 from {{ ref('stg_public_events') }} where {{ bucket_filter('actor_id') }}
    union all select actor_id, day, repo_id, n_pushes, 0 from {{ ref('stg_push_daily') }} where {{ bucket_filter('actor_id') }}
)
select {{ bucket_col('u.actor_id') }} as bucket, u.actor_id, u.day,
       sum(u.n)::integer as n_events,
       count(distinct u.repo_id)::integer as n_repos,
       sum(u.stars)::integer as n_stars_given
from u
join bounds b on b.actor_id = u.actor_id and u.day >= b.lo and u.day <= b.hi
group by 1, 2, 3
