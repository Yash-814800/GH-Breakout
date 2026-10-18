{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
-- depends_on: {{ source('lake', 'WatchEvent') }}
{#
  First star per (repo_id, actor_id) from WatchEvent. Re-stars are dropped, unstars are invisible.
  Materialised and built one repo_id hash bucket at a time (`breakout build history`, ADR-020): the
  "first star" window needs all history of a (repo, actor) pair and ~600 M rows do not fit in the
  memory cap in one statement. Rows are clustered by bucket.
#}
select
    {{ bucket_col('e.repo_id') }} as bucket,
    e.repo_id,
    e.actor_id,
    e.created_at as starred_at,
    e.event_id,
    e.detail_level
from {{ lake_events('WatchEvent') }} as e
anti join {{ ref('stg_bot_actors') }} as b on b.actor_id = e.actor_id
where {{ window_filter('e.created_at') }} and {{ bucket_filter('e.repo_id') }}
qualify row_number() over (partition by e.repo_id, e.actor_id order by e.created_at, e.event_id) = 1
