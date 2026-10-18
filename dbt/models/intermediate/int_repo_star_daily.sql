{{ config(materialized='incremental', unique_key='bucket', incremental_strategy='delete+insert') }}
{#
  Grain (repo_id, day) over ALL repos: first-star counts per UTC day. The only all-repo daily
  table (stars are needed to define candidates). Restars are dropped upstream (stg_stars).
  Built per repo_id hash bucket (ADR-020).
#}
select bucket, repo_id, starred_at::date as day, count(*)::integer as n_stars
from {{ ref('stg_stars') }}
where {{ ('bucket = ' ~ var('bucket')) if var('bucket', none) is not none else 'true' }}
group by 1, 2, 3
