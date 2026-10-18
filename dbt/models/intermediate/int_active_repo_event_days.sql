{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Grain (repo_id, day) for star-active repos: non-bot events of all kept types (stars included,
  pushes included), with the earliest event time of the day. Feeds birth detection and the
  mirror-like share without a second scan of the lake. Built in 4 repo_id hash buckets
  (n_buckets=4 for this model): one statement over all repos spilled > 16 GB and stalled (ADR-020).
#}
{% set parts = [
    ('stg_stars', 'starred_at'), ('stg_forks', 'created_at'), ('stg_issues', 'created_at'),
    ('stg_issue_comments', 'created_at'), ('stg_pull_requests', 'created_at'),
    ('stg_pr_reviews', 'created_at'), ('stg_releases', 'created_at'), ('stg_creates', 'created_at'),
    ('stg_public_events', 'created_at')] %}
with active as (
    select repo_id from {{ ref('int_star_active_repos') }} where {{ bucket_filter('repo_id') }}
)
select {{ bucket_col('repo_id') }} as bucket, repo_id, day, min(first_at) as first_at, sum(n)::integer as n_events
from (
    {% for m, col in parts %}
    select t.repo_id, t.{{ col }}::date as day, min(t.{{ col }}) as first_at, count(*) as n
    from {{ ref(m) }} t
    semi join active using (repo_id)
    group by 1, 2
    union all
    {% endfor %}
    select p.repo_id, p.day, p.day::timestamp as first_at, sum(p.n_pushes) as n
    from {{ ref('stg_push_daily') }} p
    semi join active using (repo_id)
    group by 1, 2
)
group by 1, 2, 3
