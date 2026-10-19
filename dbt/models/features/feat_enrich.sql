{{ config(materialized='incremental', unique_key=['bucket', 'snapshot_date'], incremental_strategy='delete+insert', on_schema_change='fail') }}
{#
  Tier C. Grain (repo_id, snapshot_date). Repo metadata: only the fields allowed by
  config/feature_dictionary.yaml `enrichment_columns` (created_at, is_fork; primary_language and owner_type as
  the documented slowly-varying exceptions, ADR-017). Not-found repos are 'Unknown' / NULL, not a default.
  Languages outside the seed `top_languages` (the 30 most frequent among candidate repos) are 'Other'.
  Hacker News (optional.hn_enabled): story COUNTS use created_at < D; points only for stories created in
  [D - 30, D - 3) because points are fetch-time values that mostly accrue in the first 3 days (ADR-019).
  With hn_enabled false the HN columns exist and are NULL.
#}
with c as (
    select repo_id, snapshot_date, bucket, birth_at, birth_source
    from {{ ref('mart_candidates') }}
    where {{ bucket_filter('repo_id') }}
),
hn as (
    select c.repo_id, c.snapshot_date,
        count(*) filter (where s.created_at >= c.snapshot_date - 14)::integer as hn_stories_before_14d,
        count(*) filter (where s.created_at >= c.snapshot_date - 3)::integer as hn_stories_before_3d,
        max(s.points) filter (where s.created_at >= c.snapshot_date - 30 and s.created_at < c.snapshot_date - 3) as hn_max_points_aged,
        max(s.created_at) as max_ts
    from c
    join {{ ref('stg_hn_stories') }} s
      on s.repo_id = c.repo_id and s.created_at < c.snapshot_date
    group by 1, 2
)
select
    c.bucket, c.repo_id, c.snapshot_date,
    case when m.primary_language is null then 'Unknown'
         when m.primary_language in (select language from {{ ref('top_languages') }}) then m.primary_language
         else 'Other' end as primary_language,
    coalesce(m.owner_type, 'Unknown') as owner_type,
    (c.birth_source = 'public_event')::integer as birth_from_public_event,
    case when m.api_created_at is not null then date_diff('day', m.api_created_at, c.birth_at)::integer end as days_api_created_to_birth,
    {% if var('hn_enabled') %}
    coalesce(h.hn_stories_before_14d, 0) as hn_stories_before_14d,
    coalesce(h.hn_stories_before_3d, 0) as hn_stories_before_3d,
    h.hn_max_points_aged,
    (h.max_ts is not null)::integer as hn_any_before,
    {% else %}
    null::integer as hn_stories_before_14d,
    null::integer as hn_stories_before_3d,
    null::integer as hn_max_points_aged,
    null::integer as hn_any_before,
    {% endif %}
    greatest(h.max_ts, c.birth_at) as _max_input_ts
from c
left join {{ ref('stg_repo_metadata') }} m on m.repo_id = c.repo_id and m.status = 'ok'
left join hn h on h.repo_id = c.repo_id and h.snapshot_date = c.snapshot_date
