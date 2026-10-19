{{ config(materialized='incremental', unique_key=['bucket', 'snapshot_date'], incremental_strategy='delete+insert', on_schema_change='fail') }}
{#
  Tier A. Grain (repo_id, snapshot_date). Owner = first segment of the repo name last seen before D
  (mart_candidates.repo_name_at_D): a display-level identity, rename and transfer noise accepted (the only
  place the name is used; the join is on this derived owner key, never on the repo name, ADR-023).
    owner_prior_repos_seen   other repos that carried a name with this owner prefix, first seen before D
    owner_prior_breakouts    ...of which are known hits before D (int_repo_first_hit.first_hit_outcome_day < D,
                             the same 60-day absolute rule as the tastemaker score)
  owner_is_org of the phase file is not built: the staging models carry no org_id, owner_type (feat_enrich)
  says the same.
#}
with c as (
    select repo_id, snapshot_date, bucket,
           lower(split_part(repo_name_at_D, '/', 1)) as owner
    from {{ ref('mart_candidates') }}
    where {{ bucket_filter('repo_id') }}
),
h as (
    select repo_id, lower(split_part(repo_name, '/', 1)) as owner, min(first_seen) as first_seen
    from {{ ref('stg_repo_name_history') }}
    where lower(split_part(repo_name, '/', 1)) in (select owner from c)
    group by 1, 2
),
o as (
    select c.repo_id, c.snapshot_date,
           count(distinct h.repo_id)::integer as owner_prior_repos_seen,
           count(distinct h.repo_id) filter (where f.first_hit_outcome_day < c.snapshot_date)::integer as owner_prior_breakouts,
           max(h.first_seen) as max_seen,
           max(f.first_hit_outcome_day) filter (where f.first_hit_outcome_day < c.snapshot_date) as max_hit_day
    from c
    join h on h.owner = c.owner and h.repo_id <> c.repo_id and h.first_seen < c.snapshot_date
    left join {{ ref('int_repo_first_hit') }} f on f.repo_id = h.repo_id
    group by 1, 2
)
select c.bucket, c.repo_id, c.snapshot_date,
       case when c.owner is null or c.owner = '' then null else coalesce(o.owner_prior_repos_seen, 0) end as owner_prior_repos_seen,
       case when c.owner is null or c.owner = '' then null else coalesce(o.owner_prior_breakouts, 0) end as owner_prior_breakouts,
       greatest(o.max_seen, o.max_hit_day::timestamp) as _max_input_ts
from c left join o using (repo_id, snapshot_date)
